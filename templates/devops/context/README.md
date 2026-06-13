# DevOps Project Template

## Overview
This template sets up a DevOps/Infrastructure-as-Code project with Terraform,
Docker, and CI/CD pipeline configurations.

## Quick Start

### 1. Initialize Terraform
```bash
cd infrastructure/
terraform init
terraform plan
terraform apply
```

### 2. Build Docker Image
```bash
docker build -t myapp:latest .
```

### 3. Project Structure
```
project/
├── infrastructure/   # Terraform IaC
├── docker/           # Dockerfiles and compose configs
├── .github/          # GitHub Actions CI/CD
├── scripts/          # Automation scripts
└── docs/             # Architecture and runbooks
```

## Included Skills
- **devops**: Docker management, server operations, deployment workflows
- **github-pr-workflow**: GitHub PR lifecycle, CI/CD pipeline management

## Recommended Workflow
1. Define infrastructure in `infrastructure/` with Terraform
2. Containerize services in `docker/`
3. Set up CI/CD in `.github/workflows/`
4. Store automation scripts in `scripts/`
5. Document architecture decisions in `docs/`
