import os
import pyttsx3
import speech_recognition as sr
from dotenv import load_dotenv
from langchain.llms import OpenAI
from langchain.memory import ConversationBufferMemory
from langchain.chains import ConversationChain, LLMChain
from langchain.prompts import PromptTemplate
from langchain.utilities import SerpAPIWrapper
from langchain.agents import initialize_agent, Tool, AgentType
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY")
llm = OpenAI(temperature=0, openai_api_key=OPENAI_API_KEY)
tts_engine = pyttsx3.init()
memory = ConversationBufferMemory()
sentiment_prompt = PromptTemplate(
    input_variables=["text"],
    template="""
Analyze the sentiment of this text: "{text}"
Is the sentiment Positive, Neutral, or Negative? Respond with just one word.
"""
)
sentiment_chain = LLMChain(llm=llm, prompt=sentiment_prompt)
search = SerpAPIWrapper(serpapi_api_key=SERPAPI_API_KEY)
tools = [
    Tool(
        name="Search",
        func=search.run,
        description="Useful for answering questions by searching the internet."
    ),
]
agent = initialize_agent(
    tools,
    llm,
    agent=AgentType.CONVERSATIONAL_REACT_DESCRIPTION,
    memory=memory,
    verbose=True
)
def speak(text):
    """Convert text to speech."""
    tts_engine.say(text)
    tts_engine.runAndWait()
def listen():
    """Listen to microphone and convert speech to text."""
    recognizer = sr.Recognizer()
    with sr.Microphone() as source:
        print("🎙️ Listening...")
        audio = recognizer.listen(source)
    try:
        query = recognizer.recognize_google(audio)
        print(f"You said: {query}")
        return query
    except Exception:
        print("Sorry, I did not understand that.")
        return ""
def main():
    speak("Hello! I am your AI assistant with web search. How can I help you today?")
    while True:
        user_input = listen()
        if user_input.lower() in ["exit", "quit", "stop"]:
            speak("Goodbye! Have a nice day.")
            break
        if user_input:
            sentiment = sentiment_chain.run(text=user_input).strip().lower()
            print(f"Sentiment detected: {sentiment}")
            if sentiment == "negative":
                prompt = f"You are an empathetic assistant. The user feels negative. Respond gently.\nUser said: {user_input}"
            elif sentiment == "positive":
                prompt = f"You are a cheerful assistant. The user feels positive. Respond warmly.\nUser said: {user_input}"
            else:
                prompt = f"You are a neutral assistant.\nUser said: {user_input}"
            try:
                response = agent.run(prompt)
            except Exception as e:
                response = "Sorry, I had trouble processing that."
            print(f"AI: {response}")
            speak(response)
if __name__ == "__main__":
    main()
