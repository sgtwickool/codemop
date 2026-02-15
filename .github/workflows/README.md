# GitHub Actions Workflows for CodeMop

This directory contains all GitHub Actions workflows for the CodeMop project.

## 📁 Workflows

### `ci.yml` - Continuous Integration
- **Trigger**: Push to `master`/`develop`, Pull Requests
- **Purpose**: Run tests across Python versions with coverage
- **Features**:
  - Python 3.9, 3.10, 3.11 test matrix
  - Code coverage reporting
  - Codecov integration

### `docker.yml` - Docker Build and Push
- **Trigger**: Push to `master`, version tags
- **Purpose**: Build and push Docker images to GitHub Container Registry
- **Features**:
  - Multi-architecture support
  - Automatic tagging
  - Docker layer caching

### `security.yml` - Security Scanning
- **Trigger**: Push to `master`/`develop`, Pull Requests, Weekly schedule
- **Purpose**: Security vulnerability scanning
- **Features**:
  - Safety: Dependency vulnerability scanning (ignores ecdsa side-channel vulnerabilities)
  - Bandit: Python security linting using configuration file
  - Trivy: Container vulnerability scanning

## 🚀 Usage

### Running Workflows Manually

1. **CI Tests**:
   ```bash
   gh workflow run ci.yml
   ```

2. **Docker Build**:
   ```bash
   gh workflow run docker.yml
   ```

3. **Security Scan**:
   ```bash
   gh workflow run security.yml
   ```

## 🔧 Configuration

### Required Secrets

- `GITHUB_TOKEN`: Automatic (provided by GitHub)
- `CODECOV_TOKEN`: For code coverage uploads (optional)

### Environment Variables

- `REGISTRY`: `ghcr.io` (GitHub Container Registry)
- `IMAGE_NAME`: `${{ github.repository }}` (automatic)

## 📊 Badges

Add these to your README.md:

```markdown
[![CI Status](https://github.com/your-repo/codemop/actions/workflows/ci.yml/badge.svg)](https://github.com/your-repo/codemop/actions/workflows/ci.yml)
[![Docker Build](https://github.com/your-repo/codemop/actions/workflows/docker.yml/badge.svg)](https://github.com/your-repo/codemop/actions/workflows/docker.yml)
[![Security Scan](https://github.com/your-repo/codemop/actions/workflows/security.yml/badge.svg)](https://github.com/your-repo/codemop/actions/workflows/security.yml)
[![Codecov](https://codecov.io/gh/your-repo/codemop/branch/main/graph/badge.svg)](https://codecov.io/gh/your-repo/codemop)
```

## 🎯 Best Practices

1. **Test Locally First**: Run tests locally before pushing
2. **Small Commits**: Keep changes small for easier debugging
3. **Monitor Workflows**: Check GitHub Actions tab for results
4. **Fix Failures Immediately**: Address CI failures promptly

## 🔍 Troubleshooting

### Common Issues

**1. Test Failures**
- Check test logs in GitHub Actions
- Run tests locally to reproduce
- Fix failing tests before pushing

**2. Docker Build Failures**
- Verify `Dockerfile.prod` is correct
- Check for missing files in build context
- Ensure proper permissions

**3. Security Scan Failures**
- Review vulnerability reports
- Update vulnerable dependencies
- Add exceptions if false positives

## 📚 Resources

- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [Docker Build Push Action](https://github.com/docker/build-push-action)
- [Codecov GitHub Action](https://github.com/codecov/codecov-action)
- [Trivy Security Scanner](https://github.com/aquasecurity/trivy-action)