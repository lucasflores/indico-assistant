import os
import chainlit as cl
from automaton_core import Automaton
from automaton_core.utils import embed_text_huggingface
from query_tools import (
    query_indico_database_tool,
    create_reference_footnotes,
    fetch_current_user_info,
    schema_context_v1
)
from database import queries
from datetime import date
import sys
sys.path.append("/Users/lucasflores/invariant")
from invariant.analyzer import LocalPolicy # type: ignore

# === Load Prompts ===
PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "prompts")

with open(os.path.join(PROMPTS_DIR, "classify_prompt.txt"), "r") as f:
    classify_prompt = f.read()

with open(os.path.join(PROMPTS_DIR, "sql_prompt.txt"), "r") as f:
    sql_prompt = f.read()

with open(os.path.join(PROMPTS_DIR, "summarize_prompt.txt"), "r") as f:
    summarize_prompt = f.read()

with open(os.path.join(PROMPTS_DIR, "sql_error_prompt.txt"), "r") as f:
    sql_error_prompt = f.read()

# Initialize policy for guardrails
policy = LocalPolicy.from_string("""
from invariant.detectors import prompt_injection

raise "Rule 1: Do not talk about Fight Club" if: 
    (msg: Message)
    "fight club" in msg.content
""")

# === Initialize Automata ===
classify_automaton = Automaton(role_prompt=classify_prompt)
sql_automaton = Automaton(role_prompt=sql_prompt)
summarize_automaton = Automaton(role_prompt=summarize_prompt)
sql_error_correction_automaton = Automaton(role_prompt=sql_error_prompt)

# === Get Static Data ===
today = date.today()
user_info = fetch_current_user_info()
print(user_info)

# === Utility Functions ===
async def classify_query(natural_language_query: str) -> dict:
    result = await classify_automaton.run(user_input=natural_language_query)
    return result if isinstance(result, dict) else eval(result)

async def generate_sql_from_query(natural_language_query: list, user_info: str, schema: str) -> str:
    messages = [
        {"role": "system", "content": f"Note that today's date is {today}, use this for any relative date queries.",
         "metadata": {"source": "system", "type": "date_info"}},
        {"role": "system", "content": f"USER INFO:\n{user_info}",
         "metadata": {"source": "system", "type": "user_info"}},
        {"role": "system", "content": f"DATABASE SCHEMA:\n{schema}",
         "metadata": {"source": "system", "type": "schema_info"}}
    ]
    for msg in natural_language_query:
        if isinstance(msg, dict) and "content" in msg:
            msg["metadata"] = msg.get("metadata", {"source": msg.get("role", "unknown")})
    messages.extend(natural_language_query)
    print(policy.analyze(messages))
    return await sql_automaton.run(user_input="", additional_messages=messages)

async def summarize_results(natural_language_query: str, results: list) -> str:
    messages = [
        {"role": "system", "content": f"Note that today's date is {today}, use this for any relative date queries.",
         "metadata": {"source": "system", "type": "date_info"}},
        {"role": "system", "content": f"QUERY:\n{natural_language_query}",
         "metadata": {"source": "system", "type": "query_info"}},
        {"role": "system", "content": f"RESULTS:\n{results}",
         "metadata": {"source": "system", "type": "result_info"}}
    ]
    print(policy.analyze(messages))
    return await summarize_automaton.run(user_input="", additional_messages=messages)

#sunday scaries squelcher
# === Chainlit Starters ===
@cl.set_starters
async def set_starters(user: cl.User | None) -> list[cl.Starter]:
    return [
        cl.Starter(
            label="Monday week starter refresh",
            message="Summarize the previous week's meetings and tasks, and provide a list of potential priorities for the week ahead.",
            icon="/public/weather-color-sun-cloud-svgrepo-com.svg",
            ),
        cl.Starter(
            label="Upcoming meetings",
            message="Detail any upcoming meetings from now until the end of the work week, and provide a summary of the agenda for each meeting.",
            icon="/public/crystal-ball-svgrepo-com.svg",
            )]

# === Chainlit Message Handler ===
@cl.on_message
async def handle_message(message: cl.Message):
    prompt = message.content
    try:
        #await cl.Message(content=policy.analyze([{
        #    "role": "user",
        #    "content": prompt,
        #    "metadata": {
        #        "source": "user",
        #        "timestamp": str(today)
        #    }
        #}])).send()
        await cl.Message(content="Searching Indico...").send()
        
        print(f"DEBUG: Starting SQL generation for prompt: {prompt}")
        # === SQL Generation ===
        sql_query = await generate_sql_from_query(
            cl.chat_context.to_openai(),
            user_info,
            schema_context_v1
        )
        print(f"DEBUG: Generated SQL query: {sql_query}")
        print(f"DEBUG: SQL query type: {type(sql_query)}")
        #await cl.Message(content=f"```sql \n{sql_query}\n ```").send()

        # === Query Database ===
        print(f"DEBUG: About to query database with SQL: {sql_query}")
        results = query_indico_database_tool(
            sql_query,
            params={"query_vector": embed_text_huggingface(prompt)}
        )
        print(f"DEBUG: Database results: {results}")

        # === Summarize Results ===
        print(f"DEBUG: About to summarize results")
        summary = await summarize_results(prompt, results)
        print(f"DEBUG: Generated summary: {summary}")
        print(f"DEBUG: Summary type: {type(summary)}")
        #await cl.Message(content=f"**Summary:**\n{summary}").send()
        await cl.Message(content=summary).send()

        # === Footnotes ===
        footnotes = create_reference_footnotes(results)
        if footnotes:
            footnote_block = '\n\n> ' + '  \n\n> '.join([f":small[{footnote}]" for footnote in footnotes])
            await cl.Message(content=f"**Footnotes**{footnote_block}").send()
        

    except Exception as e:
        print(f"DEBUG: Exception occurred: {e}")
        print(f"DEBUG: Exception type: {type(e)}")
        import traceback
        traceback.print_exc()
        await cl.Message(content=f"❌ Something went wrong:\n`{str(e)}`").send()

