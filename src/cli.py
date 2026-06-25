"""CLI for Release Notes Agent"""

import logging
import os
import click
import sys
import requests

from src.agent.release_notes_agent import ReleaseNotesAgent
from src.agent.enhanced_release_notes_agent import EnhancedReleaseNotesAgent
from src.config import config

logger = logging.getLogger(__name__)


def setup_logging(log_level: str = "INFO"):
    """Setup logging with specified level"""
    numeric_level = getattr(logging, log_level.upper(), None)
    if not isinstance(numeric_level, int):
        numeric_level = logging.INFO

    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    for logger_name in ['src.agent', 'src.agent.release_notes_agent', 'src.agent.tools', 'src.agent.exporters']:
        logging.getLogger(logger_name).setLevel(numeric_level)


@click.group()
@click.option('--log-level', default='INFO', type=click.Choice(['DEBUG', 'INFO', 'WARNING', 'ERROR']), help='Logging level')
@click.pass_context
def cli(ctx, log_level):
    """Release Notes Agent - Generate release notes from GitHub PRs"""
    setup_logging(log_level)
    ctx.ensure_object(dict)
    ctx.obj['log_level'] = log_level


@cli.command()
@click.argument('pr_url')
@click.option('--version', default=None, help='Release version')
@click.option('--pdf', is_flag=True, default=True, help='Generate PDF')
@click.option('--enhanced', is_flag=True, default=False, help='Use enhanced agent with full deployment guide')
@click.pass_context
def generate(ctx, pr_url: str, version: str, pdf: bool, enhanced: bool):
    """Generate release notes from a GitHub PR URL.

    Example:
        python main.py generate https://github.com/owner/repo/pull/123 --version 1.2.0
        python main.py generate https://github.com/owner/repo/pull/123 --version 1.2.0 --enhanced
    """
    try:
        config.pdf.enabled = pdf

        if enhanced:
            click.echo("🚀 Using enhanced agent with deployment guide...")
            agent = EnhancedReleaseNotesAgent()
            result = agent.generate_and_export(pr_url, version or config.release.version)

            click.echo(f"\n✅ Release notes generated successfully!")
            click.echo(f"Version: {result['release_notes'].version}")
            click.echo(f"PR: #{result['release_notes'].pr_number}")
            click.echo(f"PDF: {result['pdf']}")
            click.echo(f"JSON: {result['json']}")

            rn = result['release_notes']
            if rn.deployment_steps:
                click.echo(f"\n📋 Deployment Steps: {len(rn.deployment_steps)}")
            if rn.overall_risk_level:
                click.echo(f"⚠️  Overall Risk: {rn.overall_risk_level.value.upper()}")
        else:
            agent = ReleaseNotesAgent()
            result = agent.generate_and_export(pr_url, version)

            click.echo(f"\n✅ Release notes generated successfully!")
            click.echo(f"Version: {result['version']}")
            click.echo(f"PR: #{result['pr_number']}")

            if "pdf" in result["files"]:
                click.echo(f"PDF: {result['files']['pdf']}")
            if "confluence" in result["files"]:
                click.echo(f"Confluence: {result['files']['confluence']}")

    except Exception as e:
        click.echo(f"❌ Error: {str(e)}", err=True)
        logger.exception(e)
        sys.exit(1)


@cli.command()
@click.argument('pr_url')
@click.option('--enhanced', is_flag=True, default=False, help='Include deployment steps and risk assessment')
@click.pass_context
def preview(ctx, pr_url: str, enhanced: bool):
    """Preview release notes without exporting

    Example:
        python main.py preview https://github.com/owner/repo/pull/123
        python main.py preview https://github.com/owner/repo/pull/123 --enhanced
    """
    try:
        if enhanced:
            agent = EnhancedReleaseNotesAgent()
            release_notes = agent.process_pr_url(pr_url)
        else:
            agent = ReleaseNotesAgent()
            release_notes = agent.process_pr_url(pr_url)

        click.echo(f"\n📋 Release Notes Preview")
        click.echo("=" * 60)
        click.echo(f"Version: {release_notes.version}")
        click.echo(f"Release Date: {release_notes.release_date.strftime('%Y-%m-%d')}")
        if release_notes.pr_author:
            click.echo(f"Author: {release_notes.pr_author}")

        click.echo(f"\nSummary:\n{release_notes.summary}")

        if release_notes.features:
            click.echo(f"\n✨ Features ({len(release_notes.features)}):")
            for change in release_notes.features[:5]:
                click.echo(f"  - {change.title}")

        if release_notes.bugfixes:
            click.echo(f"\n🐛 Bug Fixes ({len(release_notes.bugfixes)}):")
            for change in release_notes.bugfixes[:5]:
                click.echo(f"  - {change.title}")

        if release_notes.breaking_changes:
            click.echo(f"\n⚠️  Breaking Changes ({len(release_notes.breaking_changes)}):")
            for change in release_notes.breaking_changes[:5]:
                click.echo(f"  - {change.title}")

        if release_notes.security_fixes:
            click.echo(f"\n🔒 Security Fixes ({len(release_notes.security_fixes)}):")
            for change in release_notes.security_fixes[:5]:
                click.echo(f"  - {change.title}")

        click.echo(f"\n📊 Statistics:")
        click.echo(f"  Total Changes: {release_notes.total_changes}")
        click.echo(f"  Files Changed: {release_notes.files_changed}")
        click.echo(f"  Additions: +{release_notes.additions}")
        click.echo(f"  Deletions: -{release_notes.deletions}")
        click.echo(f"  Overall Risk: {release_notes.overall_risk_level.value.upper()}")

        if enhanced and release_notes.deployment_steps:
            click.echo(f"\n🚀 Deployment Steps ({len(release_notes.deployment_steps)}):")
            for step in release_notes.deployment_steps[:5]:
                click.echo(f"  {step.order}. [{step.environment.upper()}] {step.title}")
                click.echo(f"     {step.description}")
                if step.commands:
                    for cmd in step.commands[:2]:
                        click.echo(f"     $ {cmd}")
            if len(release_notes.deployment_steps) > 5:
                click.echo(f"  ... and {len(release_notes.deployment_steps) - 5} more steps")

        if enhanced and release_notes.testing_recommendations:
            click.echo(f"\n🧪 Testing Recommendations ({len(release_notes.testing_recommendations)}):")
            for rec in release_notes.testing_recommendations[:3]:
                click.echo(f"  [{rec.priority.upper()}] {rec.title}: {rec.description}")

    except Exception as e:
        click.echo(f"❌ Error: {str(e)}", err=True)
        logger.exception(e)
        sys.exit(1)


@cli.command("analyze-repo")
@click.argument("repo_url")
@click.option("--output-dir", default="./cicd_contexts", show_default=True,
              help="Directory where the context file will be saved")
@click.option("--force", is_flag=True, default=False,
              help="Overwrite existing context file if present")
@click.pass_context
def analyze_repo(ctx, repo_url: str, output_dir: str, force: bool):
    """Analyze a GitHub repo and generate a cicd_context file for it.

    The file is saved as <output_dir>/<owner>_<repo>.md and will be
    automatically used by the --enhanced generator for PRs from that repo.

    Example:
        python main.py analyze-repo https://github.com/owner/repo
    """
    import re as _re
    from src.agent.tools.repo_analyzer import RepoAnalyzer
    from src.agent.tools.document_generator import DocumentGenerator

    token = config.github.token
    if not token:
        click.echo("❌ GITHUB_TOKEN not set", err=True)
        sys.exit(1)

    doc_gen = DocumentGenerator(
        llm_config=config.llm,
        language=config.llm.document_language,
    )
    analyzer = RepoAnalyzer(github_token=token, document_generator=doc_gen)

    try:
        click.echo(f"Analyzing {repo_url} ...")
        repo_full_name, context_md = analyzer.analyze(repo_url)

        slug = repo_full_name.replace("/", "_")
        os.makedirs(output_dir, exist_ok=True)
        out_path = os.path.join(output_dir, f"{slug}.md")

        if os.path.exists(out_path) and not force:
            click.echo(f"⚠️  {out_path} already exists. Use --force to overwrite.")
            sys.exit(1)

        with open(out_path, "w", encoding="utf-8") as f:
            f.write(context_md)

        click.echo(f"✅ Context saved to {out_path}")
        click.echo(f"   It will be auto-used for future PRs from {repo_full_name}")

    except Exception as e:
        click.echo(f"❌ Error: {str(e)}", err=True)
        logger.exception(e)
        sys.exit(1)


@cli.command("list-models")
@click.option("--raw", is_flag=True, default=False, help="Print raw JSON for the first model (for debugging)")
@click.pass_context
def list_models(ctx, raw):
    """List AI models available via GitHub Models for your token

    Example:
        python main.py list-models
        python main.py list-models --raw
    """
    import json as _json

    token = config.github.token
    if not token:
        click.echo("❌ GITHUB_TOKEN not set", err=True)
        sys.exit(1)

    try:
        response = requests.get(
            "https://models.github.ai/catalog/models",
            headers={
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=15,
        )
        if not response.ok:
            click.echo(f"❌ API error {response.status_code}: {response.text}", err=True)
            sys.exit(1)

        data = response.json()
        models = data if isinstance(data, list) else data.get("models", [])

        if raw and models:
            click.echo(_json.dumps(models[0], indent=2))
            return

        click.echo(f"\n{'API Model ID':<40} {'Tier':<8} {'Display Name'}")
        click.echo("-" * 90)
        for m in sorted(models, key=lambda x: x.get("publisher", "") + x.get("id", "")):
            model_id = m.get("id", "")
            display = m.get("name", "")
            tier = m.get("rate_limit_tier", "")
            click.echo(f"{model_id:<40} {tier:<8} {display}")

        click.echo(f"\nTotal: {len(models)} models")
        click.echo("\nSet COPILOT_MODEL=<API Model ID> in your .env to use a model.")

    except Exception as e:
        click.echo(f"❌ Error: {str(e)}", err=True)
        sys.exit(1)


if __name__ == '__main__':
    cli()
