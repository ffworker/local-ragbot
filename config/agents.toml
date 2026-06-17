[defaults]
default_agent = "local_answerer"
source_checker = "source_checker"
final_formatter = "final_formatter"

[[agents]]
id = "local_answerer"
display_name = "Local Answerer"
description = "Default RAG assistant for answering from local files."
task = "Answer questions using only retrieved local context."
model = "llama3.2:1b"
datasets = ["default"]
allowed_tools = ["retrieve", "generate"]
can_call = ["source_checker"]
fallback_agent = "extractive_answerer"
max_chunks = 4
min_score = 0.12
temperature = 0.1
output_style = "concise"

system_prompt = """
You are a local RAG assistant.
Answer only from the provided local context.
If the context does not contain the answer, say that the local documents do not contain it.
Cite source names.
"""

route_keywords = ["default", "general", "notes", "docs"]


[[agents]]
id = "coach_agent"
display_name = "Coach Agent"
description = "Fitness and Coach Potato project assistant."
task = "Answer questions about training plans, exercises, Coach Potato app notes, and fitness logs."
model = "llama3.2:1b"
datasets = ["coach-potato"]
allowed_tools = ["retrieve", "generate"]
can_call = ["source_checker"]
fallback_agent = "local_answerer"
max_chunks = 6
min_score = 0.10
temperature = 0.2
output_style = "practical"

system_prompt = """
You are a fitness/project assistant for Coach Potato.
Use only the local Coach Potato dataset.
Give practical, structured answers.
Do not invent progress data that is not in the local files.
"""

route_keywords = ["coach", "training", "workout", "exercise", "pushup", "handstand", "calisthenics"]


[[agents]]
id = "devops_agent"
display_name = "DevOps Agent"
description = "DevOps, homelab, Kubernetes, Ansible, Docker, and CI/CD assistant."
task = "Answer technical questions from local DevOps documentation."
model = "llama3.2:1b"
datasets = ["devops", "homelab"]
allowed_tools = ["retrieve", "generate"]
can_call = ["source_checker"]
fallback_agent = "local_answerer"
max_chunks = 8
min_score = 0.10
temperature = 0.1
output_style = "step-by-step"

system_prompt = """
You are a local DevOps assistant.
Use only retrieved local documentation.
Prefer exact commands and short explanations.
Do not assume cluster state unless it is in the local context.
"""

route_keywords = ["docker", "compose", "kubernetes", "k8s", "ansible", "terraform", "ci", "cd", "github", "ollama"]


[[agents]]
id = "extractive_answerer"
display_name = "Extractive Answerer"
description = "Fallback mode without LLM generation."
task = "Return the most relevant local excerpts."
model = ""
datasets = ["default"]
allowed_tools = ["retrieve"]
can_call = []
fallback_agent = ""
max_chunks = 4
min_score = 0.12
temperature = 0.0
output_style = "excerpts"

system_prompt = ""

route_keywords = []


[[agents]]
id = "source_checker"
display_name = "Source Checker"
description = "Checks whether the draft answer is grounded in the retrieved sources."
task = "Verify that the answer only uses the provided local context."
model = "llama3.2:1b"
datasets = []
allowed_tools = ["verify"]
can_call = ["final_formatter"]
fallback_agent = "final_formatter"
max_chunks = 0
min_score = 0.0
temperature = 0.0
output_style = "verdict"

system_prompt = """
You check whether an answer is grounded in the supplied local context.
If unsupported claims exist, flag them.
Prefer strictness over helpful guessing.
"""

route_keywords = []


[[agents]]
id = "final_formatter"
display_name = "Final Formatter"
description = "Formats the final answer for the user."
task = "Make the final response readable and concise."
model = ""
datasets = []
allowed_tools = ["format"]
can_call = []
fallback_agent = ""
max_chunks = 0
min_score = 0.0
temperature = 0.0
output_style = "clean"

system_prompt = ""

route_keywords = []
