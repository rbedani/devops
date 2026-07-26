"""Outcome classifier — maps auto-apply outcomes to status values."""


def classify_outcome(outcome: str) -> str:
    """Map an auto-apply outcome string to a status value.

    Args:
        outcome: One of 'success', 'timeout', '404', 'network_error',
                 'register_wall', 'login_required', or other.

    Returns:
        One of the 4 non-empty status values: 'postulado',
        'needs-registration', 'auto-apply-failed-unavailable',
        'general-error'.
    """
    outcomes_to_status = {
        "success": "postulado",
        "timeout": "auto-apply-failed-unavailable",
        "404": "auto-apply-failed-unavailable",
        "network_error": "auto-apply-failed-unavailable",
        "register_wall": "needs-registration",
        "login_required": "needs-registration",
    }
    return outcomes_to_status.get(outcome, "general-error")