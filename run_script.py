import time
import random
import asyncio
from datetime import datetime
from main import make_mech_request
from db import initialize_db, insert_request_id


prompts = [
    'Will India host the G20 summit in 2024?',
    'Will Donald Trump be the Republican nominee for the 2024 US Presidential election?',
    'Will the Summer Olympics take place in Paris in 2024?',
    'Will the UK rejoin the European Union in 2024?',
    'Will Brazil host the FIFA World Cup in 2024?',
    'Will Tesla become the most valuable company in the world by 2024?',
    'Will the James Webb Space Telescope make a groundbreaking discovery by 2024?',
    'Will the global economy enter a recession in 2024?',
    'Will a new COVID-19 variant emerge and cause widespread disruptions in 2024?',
    'Will the United Nations adopt a new global climate agreement by 2024?',
    'Will the European Union introduce a digital currency by 2024?',
    'Will NASA send humans to Mars by 2024?',
    'Will the UK and the EU finalize a post-Brexit trade deal by 2024?',
    'Will China and the US reach a new trade agreement by 2024?',
    'Will a new technology breakthrough revolutionize the energy sector by 2024?',
    'Will the United States rejoin the Iran nuclear deal by 2024?',
    'Will the United Nations achieve any of its Sustainable Development Goals by 2024?',
    'Will a new gene-editing technology be approved for human use by 2024?',
    'Will a new artificial intelligence system surpass human performance in a specific field by 2024?',
    'Will a new space tourism company emerge and send civilians to space by 2024?',
    'Will Russia and Ukraine reach a peace agreement by 2024?',
    'Will a new medical breakthrough significantly extend human lifespan by 2024?',
    "Will the world's first quantum computer become operational by 2024?",
    'Will a new renewable energy source become commercially viable by 2024?',
    'Will a new social media platform overtake Facebook or Twitter by 2024?',
    'Will a new cryptocurrency emerge as a major global currency by 2024?',
    'Will a new autonomous vehicle company dominate the self-driving car market by 2024?',
    "Will a new cyber attack target a major country's infrastructure by 2024?",
    'Will a new cancer treatment prove to be a significant breakthrough by 2024?',
    'Will a new space exploration mission discover evidence of extraterrestrial life by 2024?',
    'Will a new climate change mitigation technology be widely adopted by 2024?',
    'Will a new international trade agreement be ratified by major economies by 2024?',
    'Will a new pandemic outbreak occur and affect the global economy by 2024?',
    'Will a new major conflict or war break out in a specific region by 2024?',
    'Will a new major merger or acquisition shake up a particular industry by 2024?',
    'Will a new election process or voting technology be implemented in a major democracy by 2024?',
    'Will a new environmental disaster or crisis unfold in a specific region by 2024?',
    'Will a new scientific discovery challenge our current understanding of the universe by 2024?',
    'Will a new human rights issue or movement gain global attention by 2024?',
    'Will a new major sports league or tournament be established by 2024?',
    'Will a new major natural disaster strike a specific region by 2024?',
    'Will a new major political scandal emerge in a particular country by 2024?',
    'Will a new major terrorist attack occur in a specific region by 2024?',
    'Will a new major data breach or cybersecurity incident affect a global company by 2024?',
    'Will a new major technological advancement disrupt a particular industry by 2024?',
    'Will a new major economic policy or reform be implemented in a major economy by 2024?',
    'Will a new major environmental policy or regulation be adopted by a significant number of countries by 2024?',
    'Will a new major humanitarian crisis unfold in a specific region by 2024?',
    'Will a new major cultural or social movement gain global prominence by 2024?',
    'Will a new major scientific breakthrough or innovation occur in a particular field by 2024?'
]

async def make_request_with_timeout(prompt, agent_id, tool, extras, timeout_duration):
    try:
        # Wrap the make_mech_request call in a task
        task = asyncio.create_task(make_mech_request(prompt, agent_id, tool=tool, extra_attributes=extras))
        return await asyncio.wait_for(task, timeout_duration)
    except asyncio.TimeoutError:
        task.cancel()  # Attempt to cancel the task
        print(f"Request timed out after {timeout_duration} seconds")
        return None

async def send_request_async(num_calls, timeout_duration):
    start_time = time.time()
    initialize_db()

    prompt = random.choice(prompts)
    agent_id = 6
    tool = 'prediction-offline'
    extras = None

    for i in range(num_calls):
        call_start_time = time.time()
        try:
            request_id = await make_request_with_timeout(prompt, agent_id, tool, extras, timeout_duration)
            if request_id is not None:
                insert_request_id(request_id)
        except Exception as e:
            print(e)
        else:
            print(f"Request {i+1} sent in {time.time() - call_start_time} seconds")
            print(f"Current time: {datetime.now()}")

    print(f"Time taken: {time.time() - start_time} seconds")

def send_request(num_calls, timeout_duration=60):
    asyncio.run(send_request_async(num_calls, timeout_duration))


if __name__ == '__main__':
    send_request(2000) # Number of requests to be sent, change as needed