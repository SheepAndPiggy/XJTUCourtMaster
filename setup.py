from setuptools import setup, find_packages

setup(
    name="XJTUCourtMaster",          # 项目名称
    version="0.1.0",                 # 版本号
    author="你的名字",
    author_email="your_email@example.com",
    description="一个用于爬取并管理场馆场次信息的工具",
    long_description=open("README.md", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/SheepAndPiggy/XJTUCourtMaster",
    packages=find_packages(),          # 自动查找项目包
    python_requires=">=3.7",           # Python 版本要求
    install_requires=[                 # 必要依赖
        "apscheduler",
        "numpy",
        "opencv-python",
        "cryptography",
        "requests",
        "flask"
    ],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent"
    ],
)
