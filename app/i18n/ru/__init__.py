"""Russian translations — merged from sub-modules."""

from app.i18n.ru.core import RU_core
from app.i18n.ru.catalog import RU_catalog
from app.i18n.ru.dashboard import RU_dashboard
from app.i18n.ru.llm import RU_llm
from app.i18n.ru.med import RU_med
from app.i18n.ru.locktimer import RU_locktimer
from app.i18n.ru.social import RU_social
from app.i18n.ru.training import RU_training
from app.i18n.ru.insights import RU_insights
from app.i18n.ru.onboarding import RU_onboarding
from app.i18n.ru.other import RU_other

RU: dict[str, str] = {}
RU.update(RU_core)
RU.update(RU_catalog)
RU.update(RU_dashboard)
RU.update(RU_llm)
RU.update(RU_med)
RU.update(RU_locktimer)
RU.update(RU_social)
RU.update(RU_training)
RU.update(RU_insights)
RU.update(RU_onboarding)
RU.update(RU_other)
