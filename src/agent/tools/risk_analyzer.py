"""Risk Analysis Tools"""

import logging
import re
from typing import List
from src.models import (
    Change, RiskAssessment, RiskLevel, ComponentType, FileChange,
    ChangeCategory, TestingRecommendation
)

logger = logging.getLogger(__name__)


def _make_rec(title: str, priority: str = "medium", checklist: List[str] = None) -> TestingRecommendation:
    """Helper: build a TestingRecommendation from a plain string."""
    return TestingRecommendation(
        title=title,
        description=title,
        priority=priority,
        checklist=checklist or [],
    )


class RiskAnalyzer:
    """Analyze risk of changes"""

    # File patterns mapped to components
    COMPONENT_PATTERNS = {
        ComponentType.INFRASTRUCTURE: [
            r'.*\.tf$',
            r'.*\.yaml$', r'.*\.yml$',
            r'.*docker-compose.*',
            r'.*kubernetes.*', r'.*k8s.*',
            r'.*\.bicep$',
        ],
        ComponentType.DATABASE: [
            r'.*migration.*\.sql$',
            r'.*schema.*',
            r'.*database.*',
        ],
        ComponentType.API: [
            r'.*openapi.*', r'.*swagger.*',
            r'.*api.*\.py$', r'.*api.*\.ts$', r'.*api.*\.js$',
        ],
        ComponentType.CONFIGURATION: [
            r'.*config.*',
            r'.*\.env.*',
            r'.*properties.*',
            r'.*settings.*',
        ],
        ComponentType.SECURITY: [
            r'.*auth.*', r'.*secret.*', r'.*crypto.*',
            r'.*certificate.*', r'.*ssl.*', r'.*tls.*',
        ],
        ComponentType.CI_CD: [
            r'.*\.github/workflows.*',
            r'.*\.gitlab-ci.*',
            r'.*Jenkinsfile.*',
            r'.*\.circleci.*',
        ],
        ComponentType.TESTING: [
            r'.*test.*', r'.*spec.*',
            r'.*coverage.*',
        ],
        ComponentType.DOCUMENTATION: [
            r'.*\.md$', r'.*README.*',
            r'.*docs/.*',
        ],
    }

    RISK_FACTORS = {
        "infrastructure": (RiskLevel.HIGH, ["Terraform/IaC changes require careful review"]),
        "database_schema": (RiskLevel.CRITICAL, ["Database schema changes require migration testing", "Plan rollback procedure"]),
        "api_breaking": (RiskLevel.CRITICAL, ["API breaking changes affect clients"]),
        "security": (RiskLevel.CRITICAL, ["Security-related changes require audit"]),
        "large_deletion": (RiskLevel.MEDIUM, ["Large code deletions - ensure no unintended removals"]),
        "large_addition": (RiskLevel.MEDIUM, ["Large code additions - thorough testing required"]),
        "merge_commit": (RiskLevel.LOW, ["Merge commit - check for conflicts"]),
        "performance": (RiskLevel.MEDIUM, ["Performance changes - benchmarking recommended"]),
        "refactoring": (RiskLevel.LOW, ["Refactoring - ensure test coverage"]),
        "configuration": (RiskLevel.HIGH, ["Configuration changes affect runtime behavior"]),
    }

    def analyze_change(self, change: Change) -> RiskAssessment:
        """Analyze risk of a change and return a RiskAssessment."""
        risk_factors = []
        affected_components = set()
        risk_level = RiskLevel.LOW
        testing_recommendations: List[TestingRecommendation] = []
        deployment_notes = None
        rollback_plan = None

        # Analyze based on category
        if change.category == ChangeCategory.BREAKING:
            risk_level = RiskLevel.CRITICAL
            risk_factors.append("Breaking changes")
            testing_recommendations.append(_make_rec("Test all affected APIs and clients", "critical"))
            deployment_notes = "Requires coordinated deployment with clients"
            rollback_plan = "Rollback version immediately if issues detected"

        elif change.category == ChangeCategory.SECURITY:
            risk_level = RiskLevel.CRITICAL
            risk_factors.append("Security fix")
            testing_recommendations.append(_make_rec("Security audit required", "critical"))
            testing_recommendations.append(_make_rec("Penetration testing for critical fixes", "high"))
            deployment_notes = "Consider fast-track deployment for security issues"
            rollback_plan = "Have backup security measures ready"

        elif change.category == ChangeCategory.PERFORMANCE:
            risk_level = RiskLevel.MEDIUM
            risk_factors.append("Performance optimization")
            testing_recommendations.append(_make_rec("Load testing required", "high"))
            testing_recommendations.append(_make_rec("Monitor performance metrics post-deployment", "medium"))

        # Analyze files
        for file_change in change.files:
            components = self._get_components_for_file(file_change.path)
            affected_components.update(components)

            if 'migration' in file_change.path.lower() or 'schema' in file_change.path.lower():
                risk_level = RiskLevel.CRITICAL
                risk_factors.append("Database schema changes")
                testing_recommendations.append(_make_rec("Test database migration on staging", "critical"))
                testing_recommendations.append(_make_rec("Prepare migration rollback script", "critical"))

            if file_change.status == "removed" and file_change.deletions > 50:
                if risk_level not in (RiskLevel.CRITICAL, RiskLevel.HIGH):
                    risk_level = RiskLevel.MEDIUM
                risk_factors.append("Large file deletion")
                testing_recommendations.append(_make_rec("Verify no dependencies on deleted files", "high"))

            if file_change.status == "added" and file_change.additions > 500:
                if risk_level not in (RiskLevel.CRITICAL, RiskLevel.HIGH):
                    risk_level = RiskLevel.MEDIUM
                risk_factors.append("Large code addition")
                testing_recommendations.append(_make_rec("Code review required", "high"))
                testing_recommendations.append(_make_rec("Unit tests for new code", "medium"))

        if "merge" in change.title.lower():
            risk_factors.append("Merge commit")

        total_changes = change.additions + change.deletions
        if total_changes > 1000:
            if risk_level not in (RiskLevel.CRITICAL, RiskLevel.HIGH):
                risk_level = RiskLevel.MEDIUM
            risk_factors.append("Large changeset")
            testing_recommendations.append(_make_rec("Comprehensive testing required", "high"))

        for component in affected_components:
            testing_recommendations.append(_make_rec(f"Test {component.value} functionality", "medium"))

        # Deduplicate by title
        seen_titles = set()
        unique_recs = []
        for rec in testing_recommendations:
            if rec.title not in seen_titles:
                seen_titles.add(rec.title)
                unique_recs.append(rec)

        risk_factors = list(set(risk_factors))

        assessment = RiskAssessment(
            risk_level=risk_level,
            risk_factors=risk_factors if risk_factors else ["Standard change"],
            affected_components=list(affected_components) if affected_components else [ComponentType.OTHER],
            testing_recommendations=unique_recs if unique_recs else [_make_rec("Standard testing", "low")],
            deployment_notes=deployment_notes,
            rollback_plan=rollback_plan,
        )

        logger.debug(f"Risk assessment for '{change.title}': {risk_level.value}")
        return assessment

    def _get_components_for_file(self, file_path: str) -> List[ComponentType]:
        """Get affected components based on file path."""
        components = []
        for component, patterns in self.COMPONENT_PATTERNS.items():
            for pattern in patterns:
                if re.match(pattern, file_path, re.IGNORECASE):
                    components.append(component)
                    break
        return components if components else [ComponentType.OTHER]

    def get_overall_risk(self, changes: List[Change]) -> RiskLevel:
        """Calculate overall risk level for all changes."""
        if not changes:
            return RiskLevel.LOW

        risk_levels = [c.risk_assessment.risk_level for c in changes if c.risk_assessment]

        if RiskLevel.CRITICAL in risk_levels:
            return RiskLevel.CRITICAL
        elif RiskLevel.HIGH in risk_levels:
            return RiskLevel.HIGH
        elif RiskLevel.MEDIUM in risk_levels:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW
