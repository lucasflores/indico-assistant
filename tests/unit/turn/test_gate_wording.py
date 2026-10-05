"""The fast path asks Jev with the document study's "revised 2" wording, in full (spec 025, T038).

The sentences are those measured in ~/thoth/scratch/indico_doc_qa_study/routing.py (REVISED_2): changing them means
measuring them again.
"""

from indico_assistant.services.knowledge import gate


def test_data_says_a_file_is_data_also_as_a_follow_up_and_when_named():
    assert gate.ROUTES["data"].endswith(
        " That includes what a file or document the conversation mentions says, as a follow-up too: its summary, its "
        "findings, a definition in it, a page or section of it. A question about a named paper, thesis, report, talk "
        "or slides asks what a file stored in Indico says, even when its subject sounds like general science."
    )


def test_chat_is_only_what_the_conversation_itself_says():
    assert (
        "a follow-up about its last answer, or about something the conversation itself says (a term, a result, "
        "a process), when no file needs reading; a request to rephrase, summarise, translate or reformat the "
        "assistant's own answers"
    ) in gate.ROUTES["chat"]


def test_a_named_paper_is_never_out_of_scope():
    assert gate.ROUTES["out_of_scope"].endswith(
        " A question about a named paper, thesis, report, talk or slides is never out of scope."
    )


def test_jev_is_asked_the_measured_routes():
    assert set(gate.questions()["route"]["criteria"]) == {"knowledge", "change", "data", "chat", "out_of_scope"}
    assert gate.questions()["route"]["criteria"] is gate.ROUTES
