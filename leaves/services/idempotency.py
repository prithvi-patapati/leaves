from leaves.models import IdempotencyLog


def execute_with_idempotency(key, action, payload, execute_fn):
    if not key:
        return execute_fn()

    existing = IdempotencyLog.objects.filter(key=key).first()
    if existing:
        return existing.response_payload

    try:
        result = execute_fn()
        IdempotencyLog.objects.create(
            key=key, action=action, request_payload=payload,
            response_payload=result if isinstance(result, dict) else {'id': getattr(result, 'id', None)},
            status='SUCCESS',
        )
        return result
    except Exception as e:
        IdempotencyLog.objects.create(
            key=key, action=action, request_payload=payload,
            response_payload={'error': str(e)},
            status='FAILED',
        )
        raise
