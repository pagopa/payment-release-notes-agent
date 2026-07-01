# Documento CI/CD per `pagopa/pagopa-receipt-pdf-service`

## Stack / struttura del progetto

Il progetto è organizzato come **monorepo** per un singolo microservizio Java, con directory dedicate per test, infrastruttura, script e configurazioni.  
Principali componenti:

- **Backend**: Java 17 (GraalVM CE), framework Quarkus.
- **API**: Documentazione OpenAPI in `/openapi/`.
- **Testing**: Directory `integration-test` e `performance-test` per test di integrazione e performance.
- **Infra**: Directory `infra` e `.devops` per IaC (Terraform, Azure Pipelines).
- **Docker**: Dockerfile principale e script in `/docker`.
- **Helm**: Chart Helm in `/helm` per il deploy su AKS.
- **Configurazione**: `.env.example`, `.editorconfig`, `.pre-commit-config.yaml`.

## Script di deployment

### Script Bash

- **Esecuzione locale**:
  - Avvio in dev mode:  
    ```bash
    ./mvnw compile quarkus:dev
    ```
  - Build Docker:  
    ```bash
    docker build --build-arg QUARKUS_PROFILE=prod --build-arg APP_NAME=pagopa-receipt-pdf-service -t pagopa-receipt-pdf-service .
    ```
  - Run Docker:  
    ```bash
    docker run -p 8080:8080 --env-file=./.env pagopa-receipt-pdf-service
    ```

- **Script di test**:
  - `integration-test/run_integration_test.sh <env>`
  - `performance-test/run_performance_test.sh <env> <test_type> <script> <db_name> <subscription_key>`

- **Script di deploy**:
  - `.github/workflows/deploy_with_github_runner.yml` utilizza l’action custom `pagopa/github-actions-template/aks-deploy@main` per il deploy su AKS.
  - Dashboard:  
    - `.github/workflows/create_dashboard.yaml` usa `opex_dashboard generate` e `terraform.sh apply <env>`.

## Pipeline CI/CD

### Tool utilizzati

- **GitHub Actions**:  
  - Workflow principali in `.github/workflows/`.
  - Automazione di build, test, scan, release, deploy.
- **Azure DevOps**:  
  - Pipeline di performance test in `.devops/performance-test-pipelines.yml`.

### Trigger

- **Pull Request**:  
  - `check_pr.yml`, `code_review.yml`, `release_deploy.yml` (su chiusura PR).
- **Push su main**:  
  - `anchore.yml`, `code_review.yml`.
- **Manuale**:  
  - `release_deploy.yml`, `create_dashboard.yaml`, `integration_test.yml`.
- **Schedule**:  
  - `anchore.yml` (scan giornaliero), `integration_test.yml` (test giornaliero).

### Fasi

- **Build**:  
  - Build Maven (`./mvnw package`), build Docker.
- **Test**:  
  - Unit test (`mvn clean verify`), integration test (`integration-test/run_integration_test.sh`), performance test (Azure DevOps).
- **Scan**:  
  - Anchore/Grype per vulnerability scan.
- **Code Review**:  
  - SonarCloud, Google Java Format.
- **Release**:  
  - Versionamento semver, release Maven, build/push Docker image.
- **Deploy**:  
  - Deploy su AKS via Helm, update OpenAPI, Terraform apply per dashboard.

## Gestione degli ambienti

- **Ambienti principali**:  
  - `dev`, `uat`, `prod`
- **Separazione ambienti**:
  - Parametri workflow (`inputs.environment`)
  - Variabili ambiente (`env` e `secrets`)
  - Directory dedicate in `.opex/<product>/env/<environment>/config.yaml`
  - Azure DevOps pipeline: variabili per ambiente (`DEV_*`, `UAT_*`)
  - Helm: namespace, cluster, resource group variabili per ambiente

## Convenzioni di naming

- **Risorse cloud**:
  - Nome app: `pagopapagopareceiptpdfservice`
  - Helm chart: `pagopa-receipt-pdf-service`
  - DB: `pagopa_receipt_pdf_servicek6` (performance test)
- **Branch**:
  - Principale: `main`
- **File**:
  - `.env.example` per variabili ambiente
  - `Dockerfile`, `Dockerfile_integration_test`
  - Script: `run_docker.sh`, `run_integration_test.sh`, `run_performance_test.sh`
- **Variabili**:
  - `QUARKUS_PROFILE`, `APP_NAME`, `CLIENT_ID`, `SUBSCRIPTION_ID`, `TENANT_ID`
- **Label PR**:
  - `[patch, minor, major, skip]` obbligatori per release

## Monitoring post-deploy

- **Dashboard**:
  - Workflow `create_dashboard.yaml` genera dashboard Azure tramite `opex_dashboard` e Terraform.
- **Prometheus**:
  - JMX Prometheus Java Agent (`jmx_prometheus_javaagent-0.19.0.jar`) integrato nel Dockerfile.
- **Azure Application Insights, Datadog, Grafana, CloudWatch**:
  - Non esplicitamente menzionati nei file, ma la presenza di dashboard Azure e Prometheus suggerisce monitoraggio su Azure e Prometheus.

## Approvazioni e branch protection

- **CODEOWNERS**:
  - Tutto il codice è sotto la responsabilità di `@pagopa/pagopa-team-core`.
- **Reviewer richiesti**:
  - Workflow `check_pr.yml` auto-assegna reviewer tramite `auto_assign.yml`.
- **Regole di merge**:
  - PR su `main` richiedono label semver (`patch`, `minor`, `major`, `skip`).
  - PR chiuse su `main` triggerano il workflow di release/deploy.
  - Formattazione e code review automatica (SonarCloud, Google Java Format).

## Processo di release

1. **Chiusura PR su main**:
   - Trigger del workflow `release_deploy.yml`.
2. **Setup**:
   - Determinazione ambiente e semver tramite action custom.
3. **Release Maven**:
   - Versionamento, tag, release tramite action `pagopa/github-actions-template/maven-release`.
4. **Build e Push Docker Image**:
   - Build Docker con argomenti (`QUARKUS_PROFILE=prod`, `APP_NAME=pagopa-receipt-pdf-service`).
   - Push su GHCR.
5. **Deploy su AKS**:
   - Deploy tramite action custom Helm (`aks-deploy`), parametri per ambiente, namespace, cluster.
6. **Aggiornamento OpenAPI**:
   - Terraform apply per aggiornare dashboard e documentazione API.
7. **Notifica**:
   - Slack notification post-test (workflow `integration_test.yml`).
8. **Step manuali/automatici**:
   - Tutto il processo è automatizzato via GitHub Actions, con possibilità di trigger manuale per release/deploy e dashboard.

---

**Nota**:  
Alcuni dettagli su monitoring avanzato (es. Application Insights, Datadog) e step manuali di approvazione non sono esplicitamente documentati nei file e potrebbero essere gestiti esternamente o in altri repository.