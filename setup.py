from setuptools import setup, find_packages
import pathlib

here = pathlib.Path(__file__).parent.resolve()

# 获取长描述从README文件
long_description = (here / "README.md").read_text(encoding="utf-8")

setup(
    name="XJTUCourtMaster",
    version="0.1.0",  # 项目版本
    description="西安交通大学移动交大APP体育场馆的监听和预约",  # 项目简短描述
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Dan",  # 替换为你的名字
    author_email="2212212998@stu.xjtu.edu.cn",  # 替换为你的邮箱
    url="https://github.com/yourusername/your-project",  # 替换为项目URL

    # 包发现配置
    packages=find_packages(where="src"),

    # 指定包目录
    package_dir={"": "src"},

    # 指定Python版本要求
    python_requires=">=3.8, <4",

    # 安装依赖
    install_requires=[
        "requests>=2.32.5,<3.0.0",
        "cryptography>=46.0.1,<47.0.0",
        "APScheduler>=3.11.0,<4.0.0",
        "Flask>=3.1.2,<4.0.0",
        "opencv-python>=4.12.0.88,<5.0.0",
        "numpy>=2.2.6,<3.0.0",
    ],

    # 可选依赖组
    extras_require={
        "dev": [
            "pytest>=6.0",
            "pytest-cov",
            "black",
            "flake8",
        ],
        "test": [
            "pytest>=6.0",
            "pytest-cov",
        ],
    },

    # 分类信息
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Build Tools",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],

    # 项目关键词
    keywords="flask, scheduler, computer-vision, web-development",

    # 包数据文件
    include_package_data=True,
)