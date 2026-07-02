from setuptools import setup, find_packages

setup(
    name="distributed-scheduler",
    version="3.1.0",
    packages=find_packages(),
    install_requires=["etcd3", "prometheus-client", "psutil"],
    entry_points={"console_scripts": ["scheduler = scheduler.cli:main"]},
)
