import pytest

from ringr_agents.conversation import Conversation
from ringr_agents.models import ConversationModel, ParserModel, ScriptExhaustedError


def test_conversation_model_returns_replies_in_order():
    model = ConversationModel(["Hola", "Adiós"])
    conversation = Conversation()

    assert model.answer_user(conversation) == "Hola"
    assert model.answer_user(conversation) == "Adiós"


def test_parser_model_returns_parsed_data_in_order():
    model = ParserModel([{"request": None}, {"request": "Cambiar tarifa"}])
    conversation = Conversation()

    assert model.parse_data(conversation) == {"request": None}
    assert model.parse_data(conversation) == {"request": "Cambiar tarifa"}


def test_parser_model_output_cannot_mutate_script():
    script = [{"request": "Cambiar tarifa"}]
    model = ParserModel(script)

    model.parse_data(Conversation())["request"] = "otra cosa"

    assert script[0] == {"request": "Cambiar tarifa"}


def test_model_raises_clear_error_when_script_is_exhausted():
    model = ConversationModel(["Hola"])
    model.answer_user(Conversation())

    with pytest.raises(ScriptExhaustedError, match="turn 2"):
        model.answer_user(Conversation())


def test_conversation_keeps_messages_in_order():
    conversation = Conversation()
    conversation.add_user_message("Hola")
    conversation.add_agent_message("¿En qué puedo ayudarte?")

    assert [m.content for m in conversation.messages] == ["Hola", "¿En qué puedo ayudarte?"]
    assert len(conversation) == 2
