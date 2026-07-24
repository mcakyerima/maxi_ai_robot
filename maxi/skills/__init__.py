"""
maxi.skills — pluggable capabilities. Adding a capability = add a Skill subclass
and register it. The orchestrator never changes.
"""
from maxi.skills.base import Skill, SkillContext, SkillRouter

__all__ = ["Skill", "SkillContext", "SkillRouter"]
