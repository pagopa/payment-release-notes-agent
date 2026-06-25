"""Data Models for Release Notes Agent"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict


class ChangeCategory(Enum):
    """Category of changes"""
    FEATURE = "feature"
    BUGFIX = "bugfix"
    BREAKING = "breaking"
    SECURITY = "security"
    PERFORMANCE = "performance"
    DOCUMENTATION = "documentation"
    REFACTOR = "refactor"
    CHORE = "chore"


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

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "path": self.path,
            "status": self.status,
            "additions": self.additions,
            "deletions": self.deletions,
            "changes": self.changes,
        }


@dataclass
class RiskAssessment:
    """Risk assessment for a change"""
    risk_level: RiskLevel
    risk_factors: List[str]
    affected_components: List[ComponentType]
    testing_recommendations: List[str]
    deployment_notes: Optional[str] = None
    rollback_plan: Optional[str] = None
    requires_downtime: bool = False

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "risk_level": self.risk_level.value,
            "risk_factors": self.risk_factors,
            "affected_components": [c.value for c in self.affected_components],
            "testing_recommendations": self.testing_recommendations,
            "deployment_notes": self.deployment_notes,
            "rollback_plan": self.rollback_plan,
            "requires_downtime": self.requires_downtime,
        }


@dataclass
class DeploymentStep:
    """A single step in the deployment process"""
    order: int
    title: str
    description: str
    commands: List[str] = field(default_factory=list)
    validation: Optional[str] = None
    environment: str = "all"

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "order": self.order,
            "title": self.title,
            "description": self.description,
            "commands": self.commands,
            "validation": self.validation,
            "environment": self.environment,
        }


@dataclass
class TestingRecommendation:
    """A testing recommendation"""
    title: str
    description: str
    priority: str  # critical, high, medium, low
    checklist: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "title": self.title,
            "description": self.description,
            "priority": self.priority,
            "checklist": self.checklist,
        }


@dataclass
class Dependency:
    """A project dependency"""
    name: str
    version: Optional[str] = None
    type: str = "runtime"  # runtime, dev, optional

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "name": self.name,
            "version": self.version,
            "type": self.type,
        }


@dataclass
class Change:
    """Represents a single change/commit"""
    title: str
    description: str
    category: ChangeCategory
    commit_hash: str
    author: str
    additions: int = 0
    deletions: int = 0
    files_changed: int = 0
    files: List[FileChange] = field(default_factory=list)
    risk_assessment: Optional[RiskAssessment] = None

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "title": self.title,
            "description": self.description,
            "category": self.category.value,
            "commit_hash": self.commit_hash,
            "author": self.author,
            "additions": self.additions,
            "deletions": self.deletions,
            "files_changed": self.files_changed,
            "files": [f.to_dict() for f in self.files],
            "risk_assessment": self.risk_assessment.to_dict() if self.risk_assessment else None,
        }


@dataclass
class Contributor:
    """Contributor information"""
    name: str
    contributions: int


@dataclass
class ReleaseNotes:
    """Release notes container"""
    version: str
    title: str
    summary: str
    release_date: datetime = field(default_factory=datetime.now)
    pr_url: Optional[str] = None
    pr_number: Optional[int] = None
    pr_author: Optional[str] = None
    pr_body: Optional[str] = None
    all_changes: List[Change] = field(default_factory=list)
    breaking_changes: List[Change] = field(default_factory=list)
    features: List[Change] = field(default_factory=list)
    bugfixes: List[Change] = field(default_factory=list)
    security_fixes: List[Change] = field(default_factory=list)
    performance_improvements: List[Change] = field(default_factory=list)
    documentation: List[Change] = field(default_factory=list)
    refactoring: List[Change] = field(default_factory=list)
    chores: List[Change] = field(default_factory=list)
    contributors: List[Contributor] = field(default_factory=list)
    files_changed: int = 0
    additions: int = 0
    deletions: int = 0
    overall_risk_level: RiskLevel = RiskLevel.LOW
    deployment_steps: List[DeploymentStep] = field(default_factory=list)
    testing_recommendations: List[TestingRecommendation] = field(default_factory=list)

    @property
    def total_changes(self) -> int:
        """Get total number of changes"""
        return len(self.all_changes)

    def add_change(self, change: Change):
        """Add a change to the release notes

        Args:
            change: Change object to add
        """
        self.all_changes.append(change)

        # Categorize the change
        if change.category == ChangeCategory.BREAKING:
            self.breaking_changes.append(change)
        elif change.category == ChangeCategory.FEATURE:
            self.features.append(change)
        elif change.category == ChangeCategory.BUGFIX:
            self.bugfixes.append(change)
        elif change.category == ChangeCategory.SECURITY:
            self.security_fixes.append(change)
        elif change.category == ChangeCategory.PERFORMANCE:
            self.performance_improvements.append(change)
        elif change.category == ChangeCategory.DOCUMENTATION:
            self.documentation.append(change)
        elif change.category == ChangeCategory.REFACTOR:
            self.refactoring.append(change)
        elif change.category == ChangeCategory.CHORE:
            self.chores.append(change)

        # Update overall risk level
        if change.risk_assessment:
            if change.risk_assessment.risk_level == RiskLevel.CRITICAL:
                self.overall_risk_level = RiskLevel.CRITICAL
            elif change.risk_assessment.risk_level == RiskLevel.HIGH and self.overall_risk_level != RiskLevel.CRITICAL:
                self.overall_risk_level = RiskLevel.HIGH
            elif change.risk_assessment.risk_level == RiskLevel.MEDIUM and self.overall_risk_level not in [RiskLevel.CRITICAL, RiskLevel.HIGH]:
                self.overall_risk_level = RiskLevel.MEDIUM

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "version": self.version,
            "title": self.title,
            "summary": self.summary,
            "release_date": str(self.release_date),
            "pr_url": self.pr_url,
            "pr_number": self.pr_number,
            "pr_author": self.pr_author,
            "total_changes": self.total_changes,
            "files_changed": self.files_changed,
            "additions": self.additions,
            "deletions": self.deletions,
            "overall_risk_level": self.overall_risk_level.value,
            "deployment_steps": [s.to_dict() for s in self.deployment_steps],
            "testing_recommendations": [r.to_dict() for r in self.testing_recommendations],
            "changes": {
                "breaking": [c.to_dict() for c in self.breaking_changes],
                "features": [c.to_dict() for c in self.features],
                "bugfixes": [c.to_dict() for c in self.bugfixes],
                "security": [c.to_dict() for c in self.security_fixes],
                "performance": [c.to_dict() for c in self.performance_improvements],
                "documentation": [c.to_dict() for c in self.documentation],
                "refactoring": [c.to_dict() for c in self.refactoring],
                "chores": [c.to_dict() for c in self.chores],
            },
        }