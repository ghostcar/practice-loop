"""Platform Social — repositories (REFACTORING.md step 5).

Sub-modules:
- profile.py      — CRUD (get/create/update/delete)
- consent.py      — record/check consent
- subjects.py     — subject registry
- relationships.py — invitations, blocks, grants (_is_blocked, INVITE_COOLDOWN_HOURS)
- notifications.py — create/list/mark-read
- publications.py — feed + CRUD
- verification.py — policies, requests, votes, quorum
- comments.py     — comments + encouragements
- moderation.py   — reports, actions, hide content

Re-exports all public names so existing imports remain unchanged:
    from app.platform.social.repositories import create_profile, ...
"""

# --- model classes re-exported for backward compatibility (imported at module
# level by the pre-split repositories.py)
from app.platform.social.models import (  # noqa: F401
    ModerationAction,
    ModerationReport,
    SocialBlock,
    SocialComment,
    SocialConsent,
    SocialEncouragement,
    SocialGrant,
    SocialNotification,
    SocialProfile,
    SocialPublication,
    SocialRelationship,
    SocialSubject,
    SocialVerificationPolicy,
    SocialVerificationRequest,
    SocialVerificationVote,
)
from app.platform.social.repositories.comments import (  # noqa: F401
    create_comment,
    create_encouragement,
    delete_comment,
    edit_comment,
    list_comments,
)
from app.platform.social.repositories.consent import (  # noqa: F401
    get_latest_consent,
    has_accepted_consent,
    record_consent,
)
from app.platform.social.repositories.moderation import (  # noqa: F401
    assign_report,
    create_moderation_action,
    create_report,
    dismiss_report,
    get_report,
    hide_comment,
    hide_publication,
    invalidate_vote,
    list_moderation_actions,
    list_reports,
    resolve_report,
)
from app.platform.social.repositories.notifications import (  # noqa: F401
    create_notification,
    list_notifications,
    mark_notification_read,
)
from app.platform.social.repositories.profile import (  # noqa: F401
    create_profile,
    delete_profile,
    get_profile,
    get_profile_by_alias,
    update_profile,
)
from app.platform.social.repositories.publications import (  # noqa: F401
    create_publication,
    get_publication,
    list_feed,
    list_owner_publications,
    withdraw_publication,
)
from app.platform.social.repositories.relationships import (  # noqa: F401
    INVITE_COOLDOWN_HOURS,
    _is_blocked,
    accept_grant,
    accept_invitation,
    block_user,
    create_grant,
    create_invitation,
    decline_invitation,
    get_relationship,
    get_relationship_by_pair,
    list_grants_for_relationship,
    list_pending_invitations,
    list_user_blocks,
    list_user_relationships,
    revoke_grant,
    revoke_relationship,
    unblock_user,
)
from app.platform.social.repositories.subjects import (  # noqa: F401
    get_subject,
    list_owner_subjects,
    register_subject,
    tombstone_subject,
    update_projection,
)
from app.platform.social.repositories.verification import (  # noqa: F401
    cast_vote,
    check_quorum_and_finalize,
    create_verification_policy,
    create_verification_request,
    get_verification_request,
)
