"""English translations — merged from sub-modules."""

from app.i18n.en.core import EN_core
from app.i18n.en.catalog import EN_catalog
from app.i18n.en.dashboard import EN_dashboard
from app.i18n.en.llm import EN_llm
from app.i18n.en.med import EN_med
from app.i18n.en.locktimer import EN_locktimer
from app.i18n.en.social import EN_social
from app.i18n.en.training import EN_training
from app.i18n.en.insights import EN_insights
from app.i18n.en.onboarding import EN_onboarding
from app.i18n.en.other import EN_other

EN: dict[str, str] = {}
EN.update(EN_core)
EN.update(EN_catalog)
EN.update(EN_dashboard)
EN.update(EN_llm)
EN.update(EN_med)
EN.update(EN_locktimer)
EN.update(EN_social)
EN.update(EN_training)
EN.update(EN_insights)
EN.update(EN_onboarding)
EN.update(EN_other)
