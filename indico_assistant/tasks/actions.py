"""Carrying out confirmed chat-action plans in Celery, as the user who confirmed them (Feature 019)."""

import logging

from indico.core.celery import celery

from indico_assistant.tasks.chat import CHAT_QUEUE


logger = logging.getLogger(__name__)


def outcome_message(plan):
    if plan.status == 'done':
        from indico.modules.events import Event

        skipped = {r['n']: r['skipped'] for r in plan.result or () if r.get('skipped')}
        lines = ['Done:', *(f'- {step.get("description", step["action"])}'
                            + (f' (not done: {skipped[step["n"]]})' if step['n'] in skipped else '')
                            for step in plan.steps)]
        event_ids = [r['created']['event_id'] for r in plan.result or ()
                     if (r.get('created') or {}).get('event_id') is not None]
        lines += [f'[Open “{event.title}” in Indico]({event.external_url})'
                  for event in map(Event.get, dict.fromkeys(event_ids)) if event is not None]
        return '\n'.join(lines)
    if plan.status == 'refused':
        return f'I did not change anything: {plan.error}'
    return plan.error or 'The plan could not be carried out; nothing was changed.'


def _enabled_actions():
    """What the admin allows now: a plan confirmed before an action was turned off does not run."""
    from indico_assistant.plugin import AssistantPlugin
    from indico_assistant.services.actions import enabled_actions
    return enabled_actions(AssistantPlugin.settings.get_all())


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
        plan = executor.run(plan_id, enabled=_enabled_actions())
    except executor.NotConfirmed:
        jobs.finish(job_id, status='failed', error='PLAN_NOT_CONFIRMABLE', message='This plan was not confirmed.')
        return
    except Exception:
        # outside the plan's own rollback (e.g. its first commit): the job must not stay pending. (The soft
        # time limit raises inside the plan, which then rolls back as failed; only the hard kill at
        # time_limit leaves a plan in 'running'.)
        logger.exception('Plan %s could not be run', plan_id)
        jobs.finish(job_id, status='failed', error='PLAN_FAILED', message=executor.FAILED_MESSAGE)
        return
    reply = outcome_message(plan)
    message_id = None
    try:
        # the plan is carried out; saving the reply in the chat must not turn that into a failure
        if plan.session_id is not None and (chat := ChatSession.query.get(plan.session_id)) is not None:
            manager = get_session_manager()
            metadata = {'plan_id': str(plan.id), 'plan_status': plan.status}
            if plan.status != 'done':
                metadata['problem'] = 'cannot_do'  # a change that did not run carries the report offer (spec 021 R4)
            message = manager.add_assistant_message(chat, reply, metadata)
            manager.commit()
            message_id = str(message.id)
    except Exception:
        logger.exception('The outcome of plan %s could not be saved in its chat', plan_id)
    jobs.finish(job_id, status='done', message_id=message_id, response=reply,
                plan=PlanView.of(plan).model_dump(mode='json'))
