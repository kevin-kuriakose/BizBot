from setuptools import setup, find_packages

with open("requirements.txt") as f:
    install_requires = [
        line for line in f.read().strip().split("\n")
        if line and not line.startswith("#")
    ]

setup(
    name="erp_assistant",
    version="0.0.1",
    description="AI-powered ERP Assistant using local Ollama LLM",
    author="BizAxl",
    author_email="dev@bizaxl.com",
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    install_requires=install_requires,
)
