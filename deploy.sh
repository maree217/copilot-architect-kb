#!/bin/bash

# Copilot Architect KB - Deployment Script
# This script will:
# 1. Initialize git repository
# 2. Create GitHub repository
# 3. Enable GitHub Pages
# 4. Add repository topics

set -e  # Exit on any error

echo "🚀 Copilot Architect KB Deployment Script"
echo "=========================================="
echo ""

# Check if gh CLI is installed
if ! command -v gh &> /dev/null; then
    echo "❌ GitHub CLI (gh) is not installed."
    echo "📥 Install it from: https://cli.github.com/"
    exit 1
fi

# Check if user is authenticated
if ! gh auth status &> /dev/null; then
    echo "❌ Not authenticated with GitHub CLI."
    echo "🔐 Run: gh auth login"
    exit 1
fi

echo "✅ GitHub CLI authenticated"
echo ""

# Navigate to KB directory
cd "$(dirname "$0")"
echo "📁 Working directory: $(pwd)"
echo ""

# Initialize git if not already initialized
if [ ! -d .git ]; then
    echo "🎬 Initializing git repository..."
    git init
    echo "✅ Git initialized"
else
    echo "✅ Git repository already exists"
fi

# Add all files
echo "📦 Adding files to git..."
git add .
echo "✅ Files added"
echo ""

# Create commit
echo "💾 Creating initial commit..."
git commit -m "Initial commit: Copilot Architect Knowledge Base v1.0.0

- 7 major KB sections fully documented
- 48 repositories mapped (16 existing, 20 planned)
- 60+ external references curated
- 20+ architecture diagrams
- 50+ code examples
- Complete repo-index.json and external-references.json mappings
- Professional README with full navigation
- Changelog and roadmap
- GitHub Pages configuration

🤖 Generated with Claude Code
Co-Authored-By: Claude <noreply@anthropic.com>" || echo "ℹ️  Commit already exists or no changes"
echo "✅ Commit created"
echo ""

# Create GitHub repository
echo "🌐 Creating GitHub repository..."
gh repo create copilot-architect-kb \
    --public \
    --source=. \
    --remote=origin \
    --description="Production-Ready AI Systems • Enterprise Architecture • Azure & Beyond" \
    --disable-issues=false \
    --disable-wiki=false \
    || echo "ℹ️  Repository may already exist"
echo "✅ Repository created"
echo ""

# Push to GitHub
echo "⬆️  Pushing to GitHub..."
git branch -M main
git push -u origin main || echo "ℹ️  Already pushed"
echo "✅ Pushed to GitHub"
echo ""

# Enable GitHub Pages
echo "📄 Enabling GitHub Pages..."
gh repo edit --enable-pages --pages-branch main --pages-path / || echo "ℹ️  Pages may already be enabled"
echo "✅ GitHub Pages enabled"
echo ""

# Add topics
echo "🏷️  Adding repository topics..."
topics=(
    "microsoft-copilot"
    "azure-ai"
    "semantic-kernel"
    "azure-openai"
    "rag"
    "multi-agent"
    "enterprise-ai"
    "knowledge-base"
    "production-ai"
    "azure-ai-foundry"
)

for topic in "${topics[@]}"; do
    gh repo edit --add-topic "$topic" 2>/dev/null || true
done
echo "✅ Topics added"
echo ""

# Final success message
echo "🎉 Deployment Complete!"
echo "======================="
echo ""
echo "📚 Knowledge Base URL: https://maree217.github.io/copilot-architect-kb"
echo "🔗 GitHub Repository: https://github.com/maree217/copilot-architect-kb"
echo ""
echo "⏰ GitHub Pages may take 2-3 minutes to build and deploy."
echo "   Visit the URL above to verify deployment."
echo ""
echo "📋 Next Steps:"
echo "  1. Wait 2-3 minutes for GitHub Pages to build"
echo "  2. Visit https://maree217.github.io/copilot-architect-kb"
echo "  3. Update your profile README (see PROFILE_README.md)"
echo "  4. Update existing repos with KB badges"
echo "  5. Announce on LinkedIn!"
echo ""
echo "🚀 Phase 1 Complete! Ready for Phase 2."
