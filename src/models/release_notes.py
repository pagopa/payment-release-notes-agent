"""Enhanced Release Notes Model"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict
from datetime import datetime
from enum import Enum


class ChangeCategory(str, Enum):
    """Categories for changes in release notes"""
    FEATURE = "Features"
    BUGFIX = "Bug Fixes"
    BREAKING = "Breaking Changes"
    PERFORMANCE = "Performance"
    DOCUMENTATION = "Documentation"
    CHORE = "Chores"
    SECURITY = "Security"
    REFACTOR = "Refactoring"
    INFRASTRUCTURE = "Infrastructure"


class RiskLevel(Enum):
    """Risk level of a change"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ComponentType(Enum):
    """Type of component affected"""
    INFRASTRUCTURE = "infrastructure"
    API = "api"
    DATABASE = "database"
    CONFIGURATION = "configuration"
    SECURITY = "security"
    PERFORMANCE = "performance"
    DOCUMENTATION = "documentation"
    TESTING = "testing"
    CI_CD = "ci/cd"
    COMPUTE = "compute"
    NETWORK = "network"
    STORAGE = "storage"
    OTHER = "other"


@dataclass
class FileChange:
    """Represents a file changed in the PR"""
    path: str
    status: str  # added, modified, removed
    additions: int = 0
    deletions: int = 0
    changes: int = 0
    patch: Optional[str] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            "path": self.path,
            "status": self.status,
            "additions": self.additions,
            "deletions": self.deletions,
            "changes": self.changes,
        }


@dataclass
class Dependency:
    """Represents a dependency change"""
    name: str
    old_version: str
    new_version: str
    component_type: ComponentType
    breaking_change: bool = False
    notes: Optional[str] = None


@dataclass
class TestingRecommendation:
    """Testing recommendation for a change"""
    title: str
    description: str
    priority: str = "medium"  # low, medium, high, critical
    checklist: List[str] = field(default_factory=list)


@dataclass
class DeploymentStep:
    """Deployment step"""
    order: int
    title: str
    description: str
    commands: List[str] = field(default_factory=list)
    validation: Optional[str] = None
    rollback: Optional[str] = None
    environment: Optional[str] = None  # dev, staging, prod


@dataclass
class RiskAssessment:
    """Risk assessment for a change"""
    risk_level: RiskLevel
    risk_factors: List[str]
    affected_components: List[ComponentType]
    testing_recommendations: List[TestingRecommendation]
    dependencies: List[Dependency] = field(default_factory=list)
    deployment_notes: Optional[str] = None
    rollback_plan: Optional[str] = None
    requires_downtime: bool = False
    estimated_duration_minutes: int = 0
    
    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            "risk_level": self.risk_level.value,
            "risk_factors": self.risk_factors,
            "affected_components": [c.value for c in self.affected_components],
            "testing_recommendations": [
                {
                    "title": tr.title,
                    "description": tr.description,
                    "priority": tr.priority,
                    "checklist": tr.checklist,
                }
                for tr in self.testing_recommendations
            ],
            "dependencies": [
                {
                    "name": d.name,
                    "old_version": d.old_version,
                    "new_version": d.new_version,
                    "breaking_change": d.breaking_change,
                }
                for d in self.dependencies
            ],
            "deployment_notes": self.deployment_notes,
            "rollback_plan": self.rollback_plan,
            "requires_downtime": self.requires_downtime,
            "estimated_duration_minutes": self.estimated_duration_minutes,
        }


@dataclass
class Change:
    """Represents a single change"""
    title: str
    description: str
    category: ChangeCategory
    pr_number: Optional[int] = None
    commit_hash: Optional[str] = None
    author: Optional[str] = None
    files_changed: List[str] = field(default_factory=list)
    files: List[FileChange] = field(default_factory=list)
    additions: int = 0
    deletions: int = 0
    risk_assessment: Optional[RiskAssessment] = None


@dataclass
class Contributor:
    """Represents a contributor"""
    name: str
    email: Optional[str] = None
    username: Optional[str] = None
    avatar_url: Optional[str] = None
    contributions: int = 1


@dataclass
class CommitInfo:
    """Represents commit information"""
    hash: str
    short_hash: str
    message: str
    author: str
    timestamp: datetime
    files_changed: int
    additions: int
    deletions: int


@dataclass
class ReleaseNotes:
    """Main Release Notes model"""
    version: str
    title: str
    summary: str
    release_date: datetime
    pr_url: str
    pr_number: int
    
    # PR Context
    pr_body: str = ""
    pr_author: str = ""
    
    # Categorized changes
    features: List[Change] = field(default_factory=list)
    bugfixes: List[Change] = field(default_factory=list)
    breaking_changes: List[Change] = field(default_factory=list)
    performance: List[Change] = field(default_factory=list)
    performance_improvements: List[Change] = field(default_factory=list)
    documentation: List[Change] = field(default_factory=list)
    chores: List[Change] = field(default_factory=list)
    security: List[Change] = field(default_factory=list)
    security_fixes: List[Change] = field(default_factory=list)
    refactoring: List[Change] = field(default_factory=list)
    infrastructure: List[Change] = field(default_factory=list)
    
    # Metadata
    contributors: List[Contributor] = field(default_factory=list)
    commits: List[CommitInfo] = field(default_factory=list)
    
    # Statistics
    total_changes: int = 0
    files_changed: int = 0
    additions: int = 0
    deletions: int = 0
    
    # Risk assessment
    overall_risk_level: RiskLevel = RiskLevel.LOW
    deployment_steps: List[DeploymentStep] = field(default_factory=list)
    rollback_steps: List[DeploymentStep] = field(default_factory=list)

    # All changes list
    all_changes: List[Change] = field(default_factory=list)

    # LLM-generated rich content (populated by EnhancedReleaseNotesAgent)
    motivation_and_context: str = ""
    change_details_narrative: str = ""
    risk_matrix_items: List[dict] = field(default_factory=list)
    deployment_prerequisites: List[str] = field(default_factory=list)
    deployment_steps_by_env: dict = field(default_factory=dict)
    rollback_plan_items: List[dict] = field(default_factory=list)
    rollback_note: str = ""
    post_deploy_health_checks: List[dict] = field(default_factory=list)
    monitoring_notes: str = ""
    environments_affected: List[str] = field(default_factory=list)
    user_impact: str = ""
    domain: str = ""
    # PR metadata (populated from GitHub API)
    source_branch: str = ""
    target_branch: str = ""
    repo_full_name: str = ""
    pr_labels: List[str] = field(default_factory=list)
    pr_draft: bool = False
    
    def get_changes_by_category(self, category: ChangeCategory) -> List[Change]:
        """Get changes by category"""
        category_map = {
            ChangeCategory.FEATURE: self.features,
            ChangeCategory.BUGFIX: self.bugfixes,
            ChangeCategory.BREAKING: self.breaking_changes,
            ChangeCategory.PERFORMANCE: self.performance,
            ChangeCategory.DOCUMENTATION: self.documentation,
            ChangeCategory.CHORE: self.chores,
            ChangeCategory.SECURITY: self.security,
            ChangeCategory.REFACTOR: self.refactoring,
            ChangeCategory.INFRASTRUCTURE: self.infrastructure,
        }
        return category_map.get(category, [])
    
    def add_change(self, change: Change):
        """Add a change to the appropriate category"""
        self.all_changes.append(change)
        
        if change.category == ChangeCategory.FEATURE:
            self.features.append(change)
        elif change.category == ChangeCategory.BUGFIX:
            self.bugfixes.append(change)
        elif change.category == ChangeCategory.BREAKING:
            self.breaking_changes.append(change)
        elif change.category == ChangeCategory.PERFORMANCE:
            self.performance.append(change)
            self.performance_improvements.append(change)
        elif change.category == ChangeCategory.DOCUMENTATION:
            self.documentation.append(change)
        elif change.category == ChangeCategory.CHORE:
            self.chores.append(change)
        elif change.category == ChangeCategory.SECURITY:
            self.security.append(change)
            self.security_fixes.append(change)
        elif change.category == ChangeCategory.REFACTOR:
            self.refactoring.append(change)
        elif change.category == ChangeCategory.INFRASTRUCTURE:
            self.infrastructure.append(change)
        
        self.total_changes += 1
        
        # Update overall risk level
        if change.risk_assessment:
            if change.risk_assessment.risk_level == RiskLevel.CRITICAL:
                self.overall_risk_level = RiskLevel.CRITICAL
            elif change.risk_assessment.risk_level == RiskLevel.HIGH and self.overall_risk_level != RiskLevel.CRITICAL:
                self.overall_risk_level = RiskLevel.HIGH
            elif change.risk_assessment.risk_level == RiskLevel.MEDIUM and self.overall_risk_level not in [RiskLevel.CRITICAL, RiskLevel.HIGH]:
                self.overall_risk_level = RiskLevel.MEDIUM
    
    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            "version": self.version,
            "title": self.title,
            "summary": self.summary,
            "release_date": self.release_date.isoformat(),
            "pr_url": self.pr_url,
            "pr_number": self.pr_number,
            "overall_risk_level": self.overall_risk_level.value,
            "statistics": {
                "total_changes": self.total_changes,
                "files_changed": self.files_changed,
                "additions": self.additions,
                "deletions": self.deletions,
            },
            "features": [self._change_to_dict(c) for c in self.features],
            "bugfixes": [self._change_to_dict(c) for c in self.bugfixes],
            "breaking_changes": [self._change_to_dict(c) for c in self.breaking_changes],
            "performance": [self._change_to_dict(c) for c in self.performance],
            "documentation": [self._change_to_dict(c) for c in self.documentation],
            "chores": [self._change_to_dict(c) for c in self.chores],
            "security": [self._change_to_dict(c) for c in self.security],
            "refactoring": [self._change_to_dict(c) for c in self.refactoring],
            "infrastructure": [self._change_to_dict(c) for c in self.infrastructure],
            "contributors": [self._contributor_to_dict(c) for c in self.contributors],
            "deployment_steps": [self._deployment_step_to_dict(s) for s in self.deployment_steps],
        }
    
    @staticmethod
    def _change_to_dict(change: Change) -> dict:
        return {
            "title": change.title,
            "description": change.description,
            "category": change.category.value,
            "pr_number": change.pr_number,
            "commit_hash": change.commit_hash,
            "author": change.author,
            "risk_assessment": change.risk_assessment.to_dict() if change.risk_assessment else None,
        }
    
    @staticmethod
    def _contributor_to_dict(contributor: Contributor) -> dict:
        return {
            "name": contributor.name,
            "username": contributor.username,
            "contributions": contributor.contributions,
        }
    
    @staticmethod
    def _deployment_step_to_dict(step: DeploymentStep) -> dict:
        return {
            "order": step.order,
            "title": step.title,
            "description": step.description,
            "commands": step.commands,
            "validation": step.validation,
            "environment": step.environment,
        }
