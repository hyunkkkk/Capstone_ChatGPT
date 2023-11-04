# The goal of this file is to provide a FastAPI application for handling
# chat requests amd generation AI-powered responses using conversation chains.
# The application uses the LangChaing library, which includes a chatOpenAI model
# for natural language processing.

# The `StreamingConversationChain` class is responsible for creating and storing
# conversation memories and generating responses. It utilizes the `ChatOpenAI` model
# and a callback handler to stream responses as they're generated.

# The application defines a `ChatRequest` model for handling chat requests,
# which includes the conversation ID and the user's message.
# The `/chat` endpoint is used to receive chat requests and generate responses.
# It utilizes the `StreamingConversationChain` instance to generate the responses and
# sends them back as a streaming response using the `StreamingResponse` class.

# PLease note that the implementation relies on certain dependencies and imports,
# which are not included in the provided code snippet.
# Ensure that all necessary packages are installed and imported
# correctly before running the application.
#
# Install dependencies:
# pip install fastapi uvicorn[standard] python-dotenv langchain openai
#
# Example of usage:
# uvicorn main:app --reload
#
# Example of request:
#
# curl --no-buffer \
#      -X POST \
#      -H 'accept: text/event-stream' \
#      -H 'Content-Type: application/json' \
#      -d '{
#            "conversation_id": "cat-conversation",
#            "message": "what'\''s their size?"
#          }' \
#      http://localhost:8000/chat
#
# Cheers,
# @jvelezmagic

import asyncio
from functools import lru_cache
from typing import AsyncGenerator

from fastapi import Depends, FastAPI
from fastapi.responses import StreamingResponse
from langchain.callbacks import AsyncIteratorCallbackHandler
from langchain.chains import ConversationChain
from langchain.chat_models import ChatOpenAI
from langchain.memory import ConversationBufferMemory
from langchain.prompts import (
    ChatPromptTemplate,
    HumanMessagePromptTemplate,
    MessagesPlaceholder,
    SystemMessagePromptTemplate,
)
from pydantic import BaseModel, BaseSettings


class Settings(BaseSettings):
    """
    Settings class for this application.
    Utilizes the BaseSettings from pydantic for environment variables.
    """

    openai_api_key: str

    class Config:
        env_file = ".env"


@lru_cache()
def get_settings():
    """Function to get and cache settings.
    The settings are cached to avoid repeated disk I/O.
    """
    return Settings()


class StreamingConversationChain:
    """
    Class for handling streaming conversation chains.
    It creates and stores memory for each conversation,
    and generates responses using the ChatOpenAI model from LangChain.
    """

    def __init__(self, openai_api_key: str, temperature: float = 0.0):
        self.memories = {}
        self.openai_api_key = openai_api_key
        self.temperature = temperature

    async def generate_response(
        self, conversation_id: str, message: str
    ) -> AsyncGenerator[str, None]:
        """
        Asynchronous function to generate a response for a conversation.
        It creates a new conversation chain for each message and uses a
        callback handler to stream responses as they're generated.
        :param conversation_id: The ID of the conversation.
        :param message: The message from the user.
        """
        callback_handler = AsyncIteratorCallbackHandler()
        llm = ChatOpenAI(
            callbacks=[callback_handler],
            streaming=True,
            temperature=self.temperature,
            openai_api_key=self.openai_api_key,
        )

        memory = self.memories.get(conversation_id)
        if memory is None:
            memory = ConversationBufferMemory(return_messages=True)
            self.memories[conversation_id] = memory

        chain = ConversationChain(
            memory=memory,
            prompt=CHAT_PROMPT_TEMPLATE,
            llm=llm,
        )

        run = asyncio.create_task(chain.arun(input=message))

        async for token in callback_handler.aiter():
            yield token

        await run


class ChatRequest(BaseModel):
    """Request model for chat requests.
    Includes the conversation ID and the message from the user.
    """

    conversation_id: str
    message: str


CHAT_PROMPT_TEMPLATE = ChatPromptTemplate.from_messages(
    [
        SystemMessagePromptTemplate.from_template(
            "당신은 주어진 articles를 기반으로 question을 답해야 합니다.\
            답할 수 있는 경우 답과 함께 근거 article를 붙여 서술하고,\
            알 수 없는 경우 '모르겠습니다.'라고 답변하세요."
        ),
        MessagesPlaceholder(variable_name="history"),
        HumanMessagePromptTemplate.from_template("{input}"),
    ]
)

app = FastAPI(dependencies=[Depends(get_settings)])

streaming_conversation_chain = StreamingConversationChain(
    openai_api_key=get_settings().openai_api_key
)


@app.post("/chat", response_class=StreamingResponse)
async def generate_response(data: ChatRequest) -> StreamingResponse:
    """Endpoint for chat requests.
    It uses the StreamingConversationChain instance to generate responses,
    and then sends these responses as a streaming response.
    :param data: The request data.
    """
    return StreamingResponse(
        streaming_conversation_chain.generate_response(
            data.conversation_id, data.message
        ),
        media_type="text/event-stream",
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app)