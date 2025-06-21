from setuptools import setup, find_packages

setup(
    name="indico_assistant",
    version="0.1.0",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    install_requires=[
        "automaton_core",
        "chainlit",
        "sqlalchemy",
        "psycopg2-binary",
        "huggingface_hub",
        "sentence_transformers",
        "pyyaml",
        "indico",
    ],
    author="Lucas Flores",
    description="Indico Assistant for database querying and event management",
    python_requires=">=3.8",
)
