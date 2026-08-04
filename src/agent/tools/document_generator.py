"""LLM-powered document section generator for release documentation."""

import json
import logging
import os
import re
import tempfile
import time
import traceback
from typing import List

logger = logging.getLogger(__name__)

_PATCH_MAX_LINES = 120
_FILES_WITH_PATCHES_MAX = 30  # max file con diff inviati all'LLM
_LLM_TIMEOUT_SECONDS = 120    # timeout per singola chiamata LLM
_LLM_MAX_RETRIES = 2          # tentativi dopo il primo fallimento
_LLM_RETRY_BACKOFF = 10       # secondi di attesa tra retry


def _truncate_patch(patch: str, max_lines: int = _PATCH_MAX_LINES) -> str:
    if not patch:
        return ""
    lines = patch.splitlines()
    if len(lines) <= max_lines:
        return patch
    return "\n".join(lines[:max_lines]) + f"\n... ({len(lines) - max_lines} more lines)"


def _is_reasoning_model(model: str) -> bool:
    if not model:
        return False
    name = model.split("/")[-1].lower()
    if name.startswith("gpt-5"):
        return True
    if name.startswith(("o1", "o3", "o4")):
        return True
    if "reasoning" in name or name.startswith("deepseek-r"):
        return True
    return False




def create_copilot_sdk_llm(llm_config):
    """Adapter around the official `github-copilot-sdk` Python package.

    This reaches the same Copilot agent the `copilot` CLI would, but:

      * it is a single runtime installed with pip. The SDK downloads a
        self-contained native binary (Node is bundled inside it), so there is no
        Node or npm to provision — the Dockerfile bakes that binary at build
        time, see COPILOT_CLI_EXTRACT_DIR there;
      * the runtime starts ONCE and the session is reused across sections,
        instead of paying process startup on every call (measured against the
        npm CLI: ~7s per subprocess vs ~3s once, then ~1s per call);
      * the reply arrives as a structured AssistantMessageData whose `.content`
        is the model's text — no stdout scraping, no code fences, no narration
        to regex around.

    The SDK API is async and this codebase is synchronous (calls happen inside
    per-job worker threads), so the adapter owns a private event loop on a
    daemon thread and dispatches coroutines onto it.

    Startup is LAZY: nothing is spawned until the first invoke(), so importing
    or constructing the adapter costs nothing and a job that never reaches the
    enrichment phase never pays for a runtime.

    Long-running hosts MUST call close() when a job finishes — see the note on
    _close_at_exit for why the atexit hook is not a substitute.
    """
    import asyncio
    import atexit
    import threading

    try:
        import copilot as copilot_sdk
    except ImportError as exc:
        raise ValueError(
            "Provider 'copilot_sdk' requires the official SDK: "
            "`pip install github-copilot-sdk` followed by "
            "`python -m copilot download-runtime`."
        ) from exc

    cfg = llm_config

    class CopilotSDKLLM:
        def __init__(self):
            self.token = cfg.copilot_token
            self.model = cfg.copilot_model or None
            self.workdir = cfg.copilot_workdir or os.path.join(
                tempfile.gettempdir(), "copilot-sdk-workdir")
            self._loop = None
            self._thread = None
            self._client = None
            self._session = None
            self._lock = threading.Lock()
            # The model that actually served the replies. When self.model is
            # None, Copilot picks one and can change that pick without any
            # deploy on our side — so record what came back rather than what we
            # asked for. Every reply carries it; we log the first one.
            self._resolved_model = None

        # ── lifecycle ────────────────────────────────────────────────────────
        def _ensure_started(self):
            with self._lock:
                if self._session is not None:
                    return
                os.makedirs(self.workdir, exist_ok=True)

                self._loop = asyncio.new_event_loop()
                self._thread = threading.Thread(
                    target=self._loop.run_forever, daemon=True, name="copilot-sdk-loop")
                self._thread.start()

                async def _boot():
                    client = copilot_sdk.CopilotClient(
                        github_token=self.token or None,
                        # Only fall back to a machine login when no token is set;
                        # in a container there is none, so this must be explicit.
                        use_logged_in_user=not bool(self.token),
                        working_directory=self.workdir,
                        log_level="error",
                    )
                    await client.start()
                    session = await client.create_session(
                        model=self.model,
                        available_tools=[],   # pure text transformation, no tools
                        streaming=False,
                    )
                    return client, session

                t0 = time.time()
                self._client, self._session = self._run(_boot(), timeout=180)
                auth = ("COPILOT_GITHUB_TOKEN (machine login disabled)"
                        if self.token else "interactive copilot login")
                requested = self.model or "<unset — Copilot picks, logged on first reply>"
                print(f"[LLM] copilot_sdk: runtime started in {time.time()-t0:.1f}s "
                      f"| auth={auth} | model={requested} "
                      f"(reused for all subsequent sections)", flush=True)
                atexit.register(self._close_at_exit)

        def _run(self, coro, timeout):
            return asyncio.run_coroutine_threadsafe(coro, self._loop).result(timeout)

        def close(self, graceful: bool = True):
            """Release the runtime. Safe to call more than once.

            `graceful=False` skips the JSON-RPC shutdown handshake — see
            _close_at_exit for why that matters.
            """
            with self._lock:
                client, loop = self._client, self._loop
                if client is None:
                    return
                self._client = self._session = None
                self._loop = None

            if graceful:
                try:
                    asyncio.run_coroutine_threadsafe(client.stop(), loop).result(30)
                except Exception:
                    pass
            if loop is not None:
                try:
                    loop.call_soon_threadsafe(loop.stop)
                except Exception:
                    pass

        def _close_at_exit(self):
            """atexit hook: abandon the runtime instead of stopping it politely.

            CPython shuts `threading` down BEFORE running atexit handlers, which
            tears down the default ThreadPoolExecutor. The SDK's JSON-RPC writer
            does `loop.run_in_executor(None, write)`, so a graceful stop at this
            point raises "cannot schedule new futures after shutdown" and dumps a
            traceback *after* the job already succeeded — pure noise.

            Skipping the handshake leaks nothing: the runtime is a child process
            and exits with the parent (verified — no orphans remain afterwards).
            Long-running hosts should still call close() explicitly per job
            rather than relying on this.
            """
            self.close(graceful=False)

        # ── invocation ───────────────────────────────────────────────────────
        @staticmethod
        def _extract_text(event) -> str:
            """Pull the assistant's text out of the returned SessionEvent."""
            if event is None:
                raise ValueError("Copilot SDK returned no event (session went idle with no reply)")
            data = getattr(event, "data", None)
            content = getattr(data, "content", None)
            if isinstance(content, str) and content.strip():
                return content
            # Some events carry a list of content blocks rather than a plain str.
            if isinstance(content, list):
                parts = [getattr(b, "text", None) or (b.get("text") if isinstance(b, dict) else None)
                         for b in content]
                joined = "".join(p for p in parts if p)
                if joined.strip():
                    return joined
            raise ValueError(
                f"Copilot SDK event carried no usable text (event={type(event).__name__}, "
                f"data={type(data).__name__})"
            )

        def _note_model(self, event) -> None:
            """Record and log the model that served this reply, once per runtime.

            Without this the logs of a finished job never say which model wrote
            the document — and when COPILOT_MODEL is unset that is not knowable
            after the fact, since Copilot's own default can shift underneath us.
            """
            if self._resolved_model is not None:
                return
            served = getattr(getattr(event, "data", None), "model", None)
            if not served:
                return
            self._resolved_model = served
            if self.model and served != self.model:
                # Copilot substituted the request (unavailable model, policy).
                print(f"[LLM] copilot_sdk: WARNING requested model={self.model!r} "
                      f"but replies are served by {served!r}", flush=True)
            else:
                print(f"[LLM] copilot_sdk: replies served by model={served}"
                      f"{'' if self.model else ' (Copilot default — COPILOT_MODEL is unset)'}",
                      flush=True)

        def invoke(self, prompt: str, max_tokens: int = 4096) -> str:
            self._ensure_started()
            event = self._run(
                self._session.send_and_wait(prompt, timeout=_LLM_TIMEOUT_SECONDS),
                timeout=_LLM_TIMEOUT_SECONDS + 30,
            )
            self._note_model(event)
            return self._extract_text(event)

    return CopilotSDKLLM()


class DocumentGenerator:
    """Generates all rich sections of a release document via LLM.

    Each public method returns a plain dict with the generated content.
    All methods fall back to empty/default values if the LLM call fails.
    """

    CONTEXTS_DIR = "./cicd_contexts"

    def __init__(self, llm_config, language: str = "Italian", cicd_context_file: str = "", github_token: str = ""):
        self.llm_config = llm_config
        self.language = language
        self._explicit_context_file = cicd_context_file
        self._github_token = github_token
        self.cicd_context = ""        # populated lazily via load_context_for_repo()
        self.llm = self._initialize_llm()

    def load_context_for_repo(self, repo_full_name: str) -> bool:
        """Resolve and load the CI/CD context for *repo_full_name*.

        Resolution order:
        1. Explicit CICD_CONTEXT_FILE env var / config value (if set and exists)
        2. cicd_contexts/<owner>_<repo>.md

        Returns True if a context was found and loaded, False otherwise. When
        False, self.cicd_context is left empty — call ensure_context_generated()
        to generate and persist one at runtime via RepoAnalyzer.
        """
        # 1. Explicit override
        if self._explicit_context_file:
            content = self._read_file(self._explicit_context_file)
            if content:
                logger.info(
                    f"CI/CD context REUSED for '{repo_full_name}' "
                    f"(explicit override file: {self._explicit_context_file})"
                )
                self.cicd_context = content
                return True

        # 2. Repo-specific file
        if repo_full_name:
            slug = repo_full_name.replace("/", "_")
            repo_path = os.path.join(self.CONTEXTS_DIR, f"{slug}.md")
            content = self._read_file(repo_path)
            if content:
                logger.info(
                    f"CI/CD context REUSED for '{repo_full_name}' "
                    f"(existing .md file: {repo_path})"
                )
                self.cicd_context = content
                return True

        logger.warning(
            f"No CI/CD context .md file found for repository '{repo_full_name}' — "
            f"will be generated at runtime before enrichment."
        )
        self.cicd_context = ""
        return False

    def ensure_context_generated(self, repo_full_name: str) -> None:
        """If no CI/CD context is currently loaded, generate one at runtime via
        RepoAnalyzer and persist it to CONTEXTS_DIR/<owner>_<repo>.md so it is
        reused for subsequent invocations (until the process/container restarts).

        A file already present under CONTEXTS_DIR — whether baked into the
        Docker image at build time, or written by an earlier invocation in
        this same container's lifetime — must NEVER be overwritten. This is
        re-checked here (not just relied upon via load_context_for_repo()) and
        enforced atomically at write time, so it holds even under concurrent
        requests for the same new repository.
        """
        if self.cicd_context or not repo_full_name:
            return

        slug = repo_full_name.replace("/", "_")
        os.makedirs(self.CONTEXTS_DIR, exist_ok=True)
        path = os.path.join(self.CONTEXTS_DIR, f"{slug}.md")

        # Defensive re-check: do NOT generate if the file already exists.
        existing = self._read_file(path)
        if existing:
            logger.info(f"CI/CD context REUSED for '{repo_full_name}' (existing .md file: {path})")
            self.cicd_context = existing
            return

        if not self._github_token:
            logger.warning("Cannot auto-generate CI/CD context: no GitHub token configured")
            return

        from src.agent.tools.repo_analyzer import RepoAnalyzer

        try:
            analyzer = RepoAnalyzer(self._github_token, self)
            _, context = analyzer.analyze(repo_full_name)
        except Exception:
            logger.exception(f"Failed to auto-generate CI/CD context for {repo_full_name}")
            return

        if not context:
            # RepoAnalyzer already logged why (e.g. empty LLM response). Do not
            # persist a placeholder — retry from scratch on the next invocation.
            return

        # Atomic exclusive create: guarantees we can NEVER clobber a file that
        # already exists, even if another request raced us here in between
        # the check above and this write.
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            logger.info(f"CI/CD context REUSED for '{repo_full_name}' (existing .md file written concurrently: {path})")
            self.cicd_context = self._read_file(path)
            return

        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(context)
        logger.info(
            f"CI/CD context CREATED for '{repo_full_name}' "
            f"(generated via RepoAnalyzer, saved to new .md file: {path})"
        )
        self.cicd_context = context

    @staticmethod
    def _read_file(path: str) -> str:
        abs_path = os.path.abspath(path)
        if not os.path.exists(abs_path):
            return ""
        with open(abs_path, "r", encoding="utf-8") as f:
            content = f.read()
        logger.info(f"Loaded CI/CD context: {abs_path} ({len(content)} chars)")
        return content

    # ─── LLM initialisation ───────────────────────────────────────────────────

    def _initialize_llm(self):
        provider = self.llm_config.provider
        if provider == "copilot_sdk":
            return create_copilot_sdk_llm(self.llm_config)
        elif provider == "openai":
            try:
                from openai import OpenAI
                return OpenAI(api_key=self.llm_config.openai_api_key)
            except ImportError:
                raise
        elif provider == "anthropic":
            try:
                from anthropic import Anthropic
                return Anthropic(api_key=self.llm_config.anthropic_api_key)
            except ImportError:
                raise
        raise ValueError(f"Unsupported LLM provider: {provider}")




    # ─── Core LLM caller ──────────────────────────────────────────────────────

    def _call_llm(self, prompt: str, max_tokens: int = 4096, section: str = "unknown") -> str:
        last_exc = None
        for attempt in range(1 + _LLM_MAX_RETRIES):
            t0 = time.time()
            print(f"[LLM] section={section} attempt={attempt+1}/{1+_LLM_MAX_RETRIES} "
                  f"provider={self.llm_config.provider} max_tokens={max_tokens} "
                  f"prompt_chars={len(prompt)}", flush=True)
            try:
                result = self._call_llm_once(prompt, max_tokens)
                elapsed = time.time() - t0
                print(f"[LLM] section={section} attempt={attempt+1} OK "
                      f"elapsed={elapsed:.1f}s response_chars={len(result)}", flush=True)
                return result
            except Exception as e:
                elapsed = time.time() - t0
                last_exc = e
                exc_type = type(e).__name__
                print(f"[LLM] section={section} attempt={attempt+1} FAILED "
                      f"elapsed={elapsed:.1f}s exc={exc_type}: {e}", flush=True)
                print(f"[LLM] traceback: {traceback.format_exc()}", flush=True)
                if attempt < _LLM_MAX_RETRIES:
                    wait = _LLM_RETRY_BACKOFF * (attempt + 1)
                    print(f"[LLM] retrying in {wait}s...", flush=True)
                    time.sleep(wait)
        print(f"[LLM] section={section} gave up after {1+_LLM_MAX_RETRIES} attempts. "
              f"Last error: {type(last_exc).__name__}: {last_exc}", flush=True)
        return ""

    def _call_llm_once(self, prompt: str, max_tokens: int = 4096) -> str:
        provider = self.llm_config.provider

        if provider == "copilot_sdk":
            # max_tokens is accepted for signature parity, but the Copilot agent
            # exposes no equivalent — surfaced so it is visible in the logs.
            print(f"[LLM] {provider}: max_tokens={max_tokens} ignored (no equivalent)", flush=True)
            return self.llm.invoke(prompt, max_tokens=max_tokens)

        elif provider == "openai":
            model = self.llm_config.openai_model
            kwargs = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "timeout": _LLM_TIMEOUT_SECONDS,
            }
            if _is_reasoning_model(model):
                kwargs["max_completion_tokens"] = max_tokens
            else:
                kwargs["temperature"] = 0.2
                kwargs["max_tokens"] = max_tokens
            resp = self.llm.chat.completions.create(**kwargs)
            return resp.choices[0].message.content

        elif provider == "anthropic":
            resp = self.llm.messages.create(
                model=self.llm_config.anthropic_model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
                timeout=_LLM_TIMEOUT_SECONDS,
            )
            return resp.content[0].text

        raise ValueError(f"Unsupported provider: {provider}")

    def _dump_raw(self, section: str, raw: str, outcome: str) -> None:
        """Persist a raw LLM response for diagnosis. No-op unless LLM_RAW_DUMP_DIR is set.

        Without this, a parse failure is indistinguishable from a transport
        failure: both end up as {} and then as empty PDF sections, with nothing
        in the logs explaining which happened.
        """
        dump_dir = getattr(self.llm_config, "llm_raw_dump_dir", "")
        if not dump_dir:
            return
        try:
            os.makedirs(dump_dir, exist_ok=True)
            stamp = time.strftime("%Y%m%d-%H%M%S")
            path = os.path.join(dump_dir, f"{stamp}_{section}_{outcome}.txt")
            with open(path, "w", encoding="utf-8") as f:
                f.write(raw)
            print(f"[JSON] section={section} raw dumped to {path}", flush=True)
        except Exception as exc:  # diagnostics must never break generation
            logger.warning(f"Could not dump raw LLM output for {section}: {exc}")

    def _call_llm_json(self, prompt: str, max_tokens: int = 4096, section: str = "unknown") -> dict:
        raw = self._call_llm(prompt, max_tokens, section=section)
        if not raw:
            # _call_llm already logged why it gave up.
            print(f"[JSON] section={section} parsed=false reason=empty_response raw_chars=0", flush=True)
            self._dump_raw(section, "", "empty")
            return {}

        original = raw
        # Strip markdown code fences if present
        raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
        raw = re.sub(r"\s*```$", "", raw.strip())

        try:
            parsed = json.loads(raw)
            print(f"[JSON] section={section} parsed=true method=direct "
                  f"raw_chars={len(original)} keys={list(parsed)[:8] if isinstance(parsed, dict) else 'array'}",
                  flush=True)
            self._dump_raw(section, original, "ok-direct")
            return parsed
        except json.JSONDecodeError as exc:
            direct_err = exc

        # Try to extract the first JSON object/array — this is what rescues a
        # response wrapped in agent narration (the common Copilot CLI shape).
        match = re.search(r"(\{.*\}|\[.*\])", raw, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group(1))
                stripped = len(raw) - len(match.group(1))
                print(f"[JSON] section={section} parsed=true method=extracted "
                      f"raw_chars={len(original)} narration_chars={stripped} "
                      f"keys={list(parsed)[:8] if isinstance(parsed, dict) else 'array'}",
                      flush=True)
                self._dump_raw(section, original, "ok-extracted")
                return parsed
            except json.JSONDecodeError as exc:
                print(f"[JSON] section={section} parsed=false reason=extract_failed "
                      f"raw_chars={len(original)} err={exc}", flush=True)
                self._dump_raw(section, original, "fail-extract")
                logger.warning(f"LLM returned non-JSON content for section={section}")
                return {}

        print(f"[JSON] section={section} parsed=false reason=no_json_found "
              f"raw_chars={len(original)} err={direct_err} head={original[:200]!r}", flush=True)
        self._dump_raw(section, original, "fail-nojson")
        logger.warning(f"LLM returned non-JSON content for section={section}")
        return {}

    # ─── Helpers ──────────────────────────────────────────────────────────────

    _EXCLUDED_EXTENSIONS = {".md", ".hcl"}

    def _relevant_files(self, files: list) -> list:
        return [f for f in files
                if not any(f.path.endswith(ext) for ext in self._EXCLUDED_EXTENSIONS)]

    def _files_summary(self, files: list) -> str:
        lines = []
        for f in self._relevant_files(files):
            lines.append(f"  - {f.path} [{f.status}] +{f.additions}/-{f.deletions}")
        return "\n".join(lines)

    def _files_with_patches(self, files: list) -> str:
        # Sort by total lines changed, take the most impactful files
        top = sorted(self._relevant_files(files), key=lambda f: f.additions + f.deletions, reverse=True)
        top = top[:_FILES_WITH_PATCHES_MAX]
        parts = []
        for f in top:
            header = f"### {f.path} [{f.status}] +{f.additions}/-{f.deletions}"
            patch = _truncate_patch(f.patch or "")
            parts.append(f"{header}\n{patch}" if patch else header)
        omitted = len(files) - len(top)
        if omitted > 0:
            parts.append(f"... ({omitted} smaller files omitted)")
        return "\n\n".join(parts)

    def _commits_summary(self, commits: list) -> str:
        return "\n".join(
            f"  - [{c['sha'][:7]}] {c['message'].splitlines()[0]}  ({c['author']})"
            for c in commits
        )

    # ─── Public section generators ────────────────────────────────────────────

    # Known environment names the LLM might use even when out of scope — used
    # only to recognise and strip them; anything else (e.g. "main", "n/a") is
    # left untouched since it isn't necessarily an environment reference.
    _KNOWN_ENV_NAMES = {"dev", "development", "uat", "staging", "stage", "test", "testing", "qa", "prod", "production"}

    @classmethod
    def _filter_to_configured_environments(cls, environments: List[str], deployment_steps: dict, rollback_steps: list) -> tuple:
        """Defensive filter: drop any environment outside the configured scope,
        even if the LLM ignored the prompt instructions and returned it anyway."""
        allowed = {e.strip().lower() for e in environments}

        filtered_steps = {
            env: steps for env, steps in (deployment_steps or {}).items()
            if env.strip().lower() in allowed
        }

        filtered_rollback = [
            r for r in (rollback_steps or [])
            if str(r.get("environment") or "").strip().lower() not in (cls._KNOWN_ENV_NAMES - allowed)
        ]

        return filtered_steps, filtered_rollback

    @classmethod
    def _filter_environments_affected(cls, environments: List[str], environments_affected: list) -> list:
        allowed = {e.strip().lower() for e in environments}
        return [e for e in (environments_affected or []) if str(e).strip().lower() in allowed]

    def generate_overview(self, pr_details: dict, commits: list, files: list, environments: List[str]) -> dict:
        """Return executive_summary, motivation_and_context, user_impact,
        environments_affected, domain.

        *environments* is the configured list of environments in scope for this
        deployment (e.g. only ["prod"]). environments_affected must be a subset
        of it — the LLM must not invent environments outside this scope.
        """
        lang = self.language
        envs = ", ".join(environments)
        cicd_block = f"\n--- CI/CD CONTEXT ---\n{self.cicd_context}\n" if self.cicd_context else ""
        prompt = f"""You are a technical writer specialising in cloud infrastructure release documentation.
Language of the output: {lang}.
{cicd_block}
Analyse this Pull Request and return a JSON object (no other text).

--- PR INFO ---
Repository: {pr_details.get('repo_full_name', 'N/A')}
PR: #{pr_details.get('number')} — {pr_details.get('title')}
Author: {pr_details.get('author')}
Source branch: {pr_details.get('head_branch', 'N/A')}
Target branch: {pr_details.get('base_branch', 'N/A')}
State: {'Draft — in revisione' if pr_details.get('draft') else pr_details.get('state', 'N/A')}
Labels: {', '.join(pr_details.get('labels', [])) or 'none'}
Stats: {pr_details.get('changed_files')} files changed, +{pr_details.get('additions')}/-{pr_details.get('deletions')} lines
Environments in scope for this release: {envs}

--- PR DESCRIPTION ---
{pr_details.get('body') or 'N/A'}

--- COMMITS ---
{self._commits_summary(commits)}

--- FILES CHANGED ---
{self._files_summary(files)}

Return this JSON structure:
{{
  "executive_summary": "3-5 sentence executive summary of what this PR does and its business/technical impact",
  "motivation_and_context": "3-6 paragraphs explaining WHY this PR exists, the problem it solves, background, expected benefits",
  "user_impact": "Impact on end users",
  "environments_affected": ["only environments from this list that are actually affected: {envs}"],
  "domain": "Domain/system involved (e.g. 'Node / Core / Node Forwarder')"
}}"""

        result = self._call_llm_json(prompt, max_tokens=3000, section="overview")
        result["environments_affected"] = self._filter_environments_affected(
            environments, result.get("environments_affected")
        )
        logger.info("Generated overview section")
        return result

    def generate_technical_analysis(self, files: list) -> dict:
        """Return change_details_narrative and risk_matrix."""
        lang = self.language
        prompt = f"""You are a senior cloud infrastructure engineer.
Language of the output: {lang}.
Analyse these modified files and return a JSON object (no other text).

--- FILES WITH DIFFS ---
{self._files_with_patches(files)}

Return this JSON structure:
{{
  "change_details_narrative": "Detailed technical analysis organised by stack/module. For each file or group of files describe: what was added/modified, which resources are created, key parameters, dependencies. Use plain text with clear subsection titles.",
  "risk_matrix": [
    {{
      "component": "Component or stack name",
      "risk_level": "BASSO|MEDIO|ALTO|CRITICO",
      "description": "Risk description",
      "impact": "Impact if the risk materialises",
      "mitigation": "Recommended mitigation action"
    }}
  ]
}}"""

        result = self._call_llm_json(prompt, max_tokens=6000, section="technical_analysis")
        logger.info(f"Generated technical analysis with {len(result.get('risk_matrix', []))} risk items")
        return result

    def generate_operations_guide(
        self,
        pr_details: dict,
        overview: dict,
        files: list,
        environments: List[str],
        owners: List[str],
    ) -> dict:
        """Return prerequisites, deployment_steps_by_env, rollback_plan_items, rollback_note.

        *owners* are the GitHub handles/teams resolved from the repository's
        CODEOWNERS for the files touched by this PR (see codeowners.py). May
        be empty if the repo has no CODEOWNERS or none of its rules matched.
        """
        lang = self.language
        envs = ", ".join(environments)
        owners_line = ", ".join(owners) if owners else "none found in CODEOWNERS for these files"
        cicd_block = f"\n--- CI/CD CONTEXT ---\n{self.cicd_context}\n" if self.cicd_context else ""
        deployment_steps_example = ",\n    ".join(
            f'"{env}": [{{"order": 1, "action": "Step description", "responsible": "one of the CODEOWNERS owners above if any, otherwise a sensible placeholder", "notes": "Optional notes"}}]'
            for env in environments
        )
        prompt = f"""You are a senior DevOps engineer.
Language of the output: {lang}.
{cicd_block}
Generate the deployment and rollback plan for this PR. Return a JSON object (no other text).
Use the CI/CD context above to generate SPECIFIC commands and steps (actual script names, pipeline names, environment codes, real tool names).
STRICT SCOPE: this release ONLY targets the following environment(s): {envs}. Do NOT generate steps for any other environment, even if the CI/CD context mentions them.

--- PR INFO ---
Repository: {pr_details.get('repo_full_name', 'N/A')}
PR: #{pr_details.get('number')} — {pr_details.get('title')}
Author: {pr_details.get('author')}
Environments to cover: {envs}
Responsible owners (resolved from CODEOWNERS for the files touched by this PR): {owners_line}
Domain: {overview.get('domain', 'N/A')}
User impact: {overview.get('user_impact', 'N/A')}

--- FILES CHANGED ---
{self._files_summary(files)}

Return this JSON structure (deployment_steps and rollback_steps must ONLY reference environments from: {envs}):
{{
  "prerequisites": [
    "Prerequisite 1",
    "Prerequisite 2"
  ],
  "deployment_steps": {{
    {deployment_steps_example}
  }},
  "rollback_steps": [
    {{"order": 1, "action": "Rollback action", "environment": "one of: {envs}", "responsible": "one of the CODEOWNERS owners above if any, otherwise a sensible placeholder", "notes": ""}}
  ],
  "rollback_note": "One sentence note on rollback impact (e.g. no existing resources modified)"
}}"""

        result = self._call_llm_json(prompt, max_tokens=6000, section="operations_guide")
        result["deployment_steps"], result["rollback_steps"] = self._filter_to_configured_environments(
            environments, result.get("deployment_steps"), result.get("rollback_steps")
        )
        logger.info("Generated operations guide")
        return result

    def generate_post_deploy_verification(self, files: list, overview: dict) -> dict:
        """Return post_deploy_health_checks and monitoring_notes."""
        lang = self.language
        cicd_block = f"\n--- CI/CD CONTEXT ---\n{self.cicd_context}\n" if self.cicd_context else ""
        prompt = f"""You are a senior QA/SRE engineer.
Language of the output: {lang}.
{cicd_block}
Generate post-deploy verification checks for this release. Return a JSON object (no other text).
Use the CI/CD context to reference the actual monitoring tools and check methods used in this repo.

--- CHANGE SUMMARY ---
Domain: {overview.get('domain', 'N/A')}
Environments: {', '.join(overview.get('environments_affected', []))}
User impact: {overview.get('user_impact', 'N/A')}

--- FILES CHANGED ---
{self._files_summary(files)}

Return this JSON structure:
{{
  "health_checks": [
    {{
      "check": "Check name",
      "method": "How to verify (e.g. Azure Portal / curl / Application Insights)",
      "expected": "Expected result"
    }}
  ],
  "monitoring_notes": "What to monitor after deploy and for how long"
}}"""

        result = self._call_llm_json(prompt, max_tokens=2000, section="post_deploy_verification")
        logger.info(f"Generated {len(result.get('health_checks', []))} health checks")
        return result
