"""Carrying out confirmed chat-action plans in Celery, as the user who confirmed them (Feature 019)."""

import logging

from indico.core.celery import celery

from indico_assistant.tasks.chat import CHAT_QUEUE


logger = logging.getLogger(__name__)


def outcome_message(plan):
    if plan.status == 'done':
        from indico.modules.events import Event

        lines = ['Done:', *(f'- {step.get("description", step["action"])}' for step in plan.steps)]
        event_ids = [r['created']['event_id'] for r in plan.result or ()
                     if (r.get('created') or {}).get('event_id') is not None]
        lines += [f'[Open “{event.title}” in Indico]({event.external_url})'
                  for event in map(Event.get, dict.fromkeys(event_ids)) if event is not None]
        return '\n'.join(lines)
    if plan.status == 'refused':
        return f'I did not change anything: {plan.error}'
    return plan.error or 'The plan could not be carried out; nothing was changed.'


# request_context: Indico's operations read session.user (services/actions/context.acting_as)
@celery.task(name='indico_assistant.execute_plan', queue=CHAT_QUEUE, request_context=True, plugin='assistant',
             ignore_result=True, soft_time_limit=60, time_limit=90)
def execute_plan(job_id, plan_id):
    from indico_assistant.models import ChatSession
    from indico_assistant.schemas.actions import PlanView
    from indico_assistant.services.actions import executor
    from indico_assistant.services.chat import jobs
    from indico_assistant.services.chat.session_manager import get_session_manager

    jobs.start(job_id)
    try:
        plan = executor.run(plan_id)
    except executor.NotConfirmed:
        jobs.finish(job_id, status='failed', error='PLAN_NOT_CONFIRMABLE', message='This plan was not confirmed.')
        return
    reply = outcome_message(plan)
    manager = get_session_manager()
    message = manager.add_assistant_message(ChatSession.query.get(plan.session_id), reply,
                                            {'plan_id': str(plan.id), 'plan_status': plan.status})
    manager.commit()
    jobs.finish(job_id, status='done', message_id=str(message.id), response=reply,
                plan=PlanView.of(plan).model_dump(mode='json'))
