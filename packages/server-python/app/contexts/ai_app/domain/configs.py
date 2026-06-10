from typing import Any

from pydantic import BaseModel


class AppConfig(BaseModel):
    """应用配置基类，各应用可扩展"""

    theme: str | None = None
    language: str = "zh-CN"
    capabilities: list[str] = []

    @classmethod
    def from_json(cls, data: dict[str, Any] | None) -> "AppConfig":
        if data is None:
            return cls()
        return cls.model_validate(data)

    def to_json(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)


class CourseCapabilityMapConfig(AppConfig):
    """APP-001 课程能力图谱配置"""

    course_id: str | None = None
    auto_refresh: bool = False
    max_nodes: int = 500


class PreviewGuideConfig(AppConfig):
    """APP-002 智能预习导学配置"""

    prerequisite_depth: int = 2
    generate_quiz: bool = True


class ResourceRecommendationConfig(AppConfig):
    """APP-003 资源推荐配置"""

    max_recommendations: int = 10
    enable_collaborative_filtering: bool = False


class ReviewPlannerConfig(AppConfig):
    """APP-004 复习巩固配置"""

    max_review_items: int = 20
    forgetting_curve_enabled: bool = True


CONFIG_CLASS_BY_CODE: dict[str, type[AppConfig]] = {
    "APP-001": CourseCapabilityMapConfig,
    "APP-002": PreviewGuideConfig,
    "APP-003": ResourceRecommendationConfig,
    "APP-004": ReviewPlannerConfig,
}


def get_config_class(code: str) -> type[AppConfig]:
    """根据应用 code 返回对应的配置类，未知应用返回基类"""
    return CONFIG_CLASS_BY_CODE.get(code, AppConfig)
