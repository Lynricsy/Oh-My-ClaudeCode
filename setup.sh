#!/bin/bash
# OMCC One-Click Setup Script for macOS/Linux
set -e

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Helper functions
write_step() {
    echo -e "\n${CYAN}[*] $1${NC}"
}

write_success() {
    echo -e "${GREEN}[OK] $1${NC}"
}

write_error() {
    echo -e "${RED}[ERROR] $1${NC}"
}

write_warning() {
    echo -e "${YELLOW}[WARN] $1${NC}"
}

# ==============================================================================
# Step 1: Check dependencies
# ==============================================================================
write_step "Step 1: Checking dependencies..."

# Check and install uv
if command -v uv &> /dev/null; then
    write_success "uv is installed"
else
    write_warning "uv is not installed, installing automatically..."
    if curl -LsSf https://astral.sh/uv/install.sh | sh; then
        export PATH="$HOME/.local/bin:$PATH"
        write_success "uv installed successfully"
    else
        write_error "Failed to install uv automatically"
        echo "Please install uv manually: https://github.com/astral-sh/uv"
        exit 1
    fi
fi

# Check claude CLI
if command -v claude &> /dev/null; then
    write_success "claude CLI is installed"
else
    write_error "claude CLI is not installed"
    echo "Please install Claude Code CLI first: https://docs.anthropic.com/en/docs/claude-code"
    exit 1
fi

# ==============================================================================
# Step 2: Install project dependencies
# ==============================================================================
write_step "Step 2: Installing project dependencies..."

cd "$SCRIPT_DIR"
if uv sync; then
    write_success "Project dependencies installed"
else
    write_error "Failed to install dependencies"
    exit 1
fi

# ==============================================================================
# Step 3: Register MCP server
# ==============================================================================
write_step "Step 3: Registering MCP server..."

# Try to remove existing omcc MCP server if it exists
claude mcp remove omcc --scope user 2>/dev/null && write_warning "Removed existing omcc MCP server" || true

# Check uv version to determine if --refresh is supported
MCP_REGISTERED=false
LAST_ERROR=""
USE_REFRESH=false
UV_VERSION_KNOWN=false

UV_VERSION_OUTPUT=$(uv --version 2>&1) || true
if [[ "$UV_VERSION_OUTPUT" =~ uv\ ([0-9]+)\.([0-9]+)\.([0-9]+) ]]; then
    UV_VERSION_KNOWN=true
    MAJOR="${BASH_REMATCH[1]}"
    MINOR="${BASH_REMATCH[2]}"
    # --refresh requires uv >= 0.4.0
    if [ "$MAJOR" -gt 0 ] || ([ "$MAJOR" -eq 0 ] && [ "$MINOR" -ge 4 ]); then
        USE_REFRESH=true
    fi
fi

if [ "$USE_REFRESH" = true ]; then
    # Try with --refresh first (disable set -e for this block)
    set +e
    REFRESH_OUTPUT=$(claude mcp add omcc --scope user --transport stdio -- uvx --refresh --from git+https://github.com/Lynricsy/Oh-My-ClaudeCode.git omcc-mcp 2>&1)
    REFRESH_EXIT_CODE=$?
    set -e

    if [ $REFRESH_EXIT_CODE -eq 0 ]; then
        MCP_REGISTERED=true
        write_success "MCP server registered (with --refresh)"
    elif echo "$REFRESH_OUTPUT" | grep -qiE "(unknown|unrecognized|unexpected|invalid).*(option|flag|argument).*--refresh|--refresh.*(unknown|unrecognized|unexpected|invalid)"; then
        # Fallback: --refresh was rejected (covers various CLI error message formats), try without it
        write_warning "--refresh option was rejected, falling back to installation without --refresh..."
        set +e
        FALLBACK_OUTPUT=$(claude mcp add omcc --scope user --transport stdio -- uvx --from git+https://github.com/Lynricsy/Oh-My-ClaudeCode.git omcc-mcp 2>&1)
        FALLBACK_EXIT_CODE=$?
        set -e
        if [ $FALLBACK_EXIT_CODE -eq 0 ]; then
            MCP_REGISTERED=true
            write_success "MCP server registered (without --refresh)"
        else
            LAST_ERROR="$FALLBACK_OUTPUT"
        fi
    else
        LAST_ERROR="$REFRESH_OUTPUT"
    fi
else
    # uv version too old or unknown, skip --refresh
    if [ "$UV_VERSION_KNOWN" = true ]; then
        write_warning "Your uv version does not support --refresh option (requires uv >= 0.4.0)"
    else
        write_warning "Could not determine uv version, skipping --refresh option"
    fi
    write_warning "Installing without --refresh..."
    write_warning "Consider upgrading uv: curl -LsSf https://astral.sh/uv/install.sh | sh"

    set +e
    FALLBACK_OUTPUT=$(claude mcp add omcc --scope user --transport stdio -- uvx --from git+https://github.com/Lynricsy/Oh-My-ClaudeCode.git omcc-mcp 2>&1)
    FALLBACK_EXIT_CODE=$?
    set -e
    if [ $FALLBACK_EXIT_CODE -eq 0 ]; then
        MCP_REGISTERED=true
        write_success "MCP server registered (without --refresh)"
    else
        LAST_ERROR="$FALLBACK_OUTPUT"
    fi
fi

if [ "$MCP_REGISTERED" = false ]; then
    write_error "Failed to register MCP server"
    echo "Error details: $LAST_ERROR"
    exit 1
fi

# ==============================================================================
# Step 4: Install Skills
# ==============================================================================
write_step "Step 4: Installing Skills..."

SKILLS_DIR="$HOME/.claude/skills"

# Create skills directory if it doesn't exist
if [ ! -d "$SKILLS_DIR" ]; then
    mkdir -p "$SKILLS_DIR"
    write_success "Created skills directory: $SKILLS_DIR"
fi

# List of all skills to install
SKILLS=("omcc-workflow" "gemini-collaboration" "frontend" "chore" "librarian" "looker")

# Install each skill
for skill in "${SKILLS[@]}"; do
    SOURCE="$SCRIPT_DIR/skills/$skill"
    if [ -d "$SOURCE" ]; then
        DEST="$SKILLS_DIR/$skill"
        rm -rf "$DEST"
        cp -r "$SOURCE" "$DEST"
        write_success "Installed $skill skill"
    else
        write_warning "$skill skill not found, skipping"
    fi
done

# ==============================================================================
# Step 5: Configure global CLAUDE.md
# ==============================================================================
write_step "Step 5: Configuring global CLAUDE.md..."

CLAUDE_MD_PATH="$HOME/.claude/CLAUDE.md"
OMCC_MARKER="# OMCC Configuration"
OMCC_CONFIG_PATH="$SCRIPT_DIR/templates/omcc-global-prompt.md"

# Create .claude directory if it doesn't exist
mkdir -p "$HOME/.claude"

if [ ! -f "$CLAUDE_MD_PATH" ]; then
    # Create new file with OMCC config
    if [ -f "$OMCC_CONFIG_PATH" ]; then
        cp "$OMCC_CONFIG_PATH" "$CLAUDE_MD_PATH"
        write_success "Created global CLAUDE.md"
    else
        write_warning "OMCC global prompt template not found at $OMCC_CONFIG_PATH"
        write_warning "Please manually copy the OMCC configuration to $CLAUDE_MD_PATH"
    fi
else
    # Check if OMCC config already exists
    if grep -qF "$OMCC_MARKER" "$CLAUDE_MD_PATH"; then
        write_warning "OMCC configuration already exists in CLAUDE.md, skipping"
    else
        # Append OMCC config
        if [ -f "$OMCC_CONFIG_PATH" ]; then
            echo "" >> "$CLAUDE_MD_PATH"
            cat "$OMCC_CONFIG_PATH" >> "$CLAUDE_MD_PATH"
            write_success "Appended OMCC configuration to CLAUDE.md"
        else
            write_warning "OMCC global prompt template not found at $OMCC_CONFIG_PATH"
            write_warning "Please manually copy the OMCC configuration to $CLAUDE_MD_PATH"
        fi
    fi
fi

# ==============================================================================
# Step 6: Configure Gemini CLI (for Frontend/Librarian/Looker)
# ==============================================================================
write_step "Step 6: Configuring Gemini CLI..."

GEMINI_DIR="$HOME/.gemini"
GEMINI_SETTINGS_SOURCE="$SCRIPT_DIR/templates/gemini/settings.json"
GEMINI_SETTINGS_PATH="$GEMINI_DIR/settings.json"
GEMINI_ENV_PATH="$GEMINI_DIR/.env"

# Check if gemini CLI is installed
if command -v gemini &> /dev/null; then
    write_success "gemini CLI is installed"

    # Create .gemini directory if it doesn't exist
    mkdir -p "$GEMINI_DIR"

    # Copy settings.json if source exists
    if [ -f "$GEMINI_SETTINGS_SOURCE" ]; then
        if [ -f "$GEMINI_SETTINGS_PATH" ]; then
            write_warning "Gemini settings.json already exists, skipping"
            write_warning "To update, manually merge: $GEMINI_SETTINGS_SOURCE"
        else
            cp "$GEMINI_SETTINGS_SOURCE" "$GEMINI_SETTINGS_PATH"
            write_success "Installed Gemini settings.json"
        fi
    fi

    # =========================================================================
    # Step 6.1: Check MCP dependencies
    # =========================================================================
    echo ""
    echo -e "${CYAN}  Checking MCP dependencies...${NC}"

    # Check Docker (required for github MCP)
    DOCKER_AVAILABLE=false
    if command -v docker &> /dev/null; then
        # Check if Docker daemon is running
        if docker info &> /dev/null; then
            DOCKER_AVAILABLE=true
            write_success "Docker is installed and running (required for github MCP)"
        else
            write_warning "Docker is installed but not running"
            write_warning "Start Docker to enable github MCP: sudo systemctl start docker"
        fi
    else
        write_warning "Docker not installed (required for github MCP)"
        write_warning "Install Docker: https://docs.docker.com/get-docker/"
    fi

    # Check npm/npx (required for firecrawl MCP)
    NPM_AVAILABLE=false
    if command -v npx &> /dev/null; then
        NPM_AVAILABLE=true
        write_success "npx is available (required for firecrawl MCP)"
    else
        write_warning "npx not found (required for firecrawl MCP)"
        write_warning "Install Node.js: https://nodejs.org/"
    fi

    # =========================================================================
    # Step 6.2: Configure API keys for MCP servers
    # =========================================================================
    echo ""
    echo -e "${CYAN}  Configuring API keys for MCP servers...${NC}"
    echo ""
    echo "============================================================"
    echo -e "${YELLOW}GitHub Personal Access Token (for github MCP)${NC}"
    echo "============================================================"
    echo ""
    echo "How to get your token:"
    echo "  1. Go to: https://github.com/settings/tokens"
    echo "  2. Click 'Generate new token' -> 'Generate new token (classic)'"
    echo "  3. Set a descriptive name (e.g., 'OMCC Gemini MCP')"
    echo "  4. Set expiration as needed (recommend: 90 days or No expiration)"
    echo "  5. Select the following scopes:"
    echo ""
    echo -e "     ${GREEN}Required scopes:${NC}"
    echo "     [x] repo              - Full control of private repositories"
    echo "         [x] repo:status   - Access commit status"
    echo "         [x] repo_deployment - Access deployment status"
    echo "         [x] public_repo   - Access public repositories"
    echo "         [x] repo:invite   - Access repository invitations"
    echo "     [x] read:org          - Read org and team membership"
    echo "     [x] read:user         - Read user profile data"
    echo "     [x] user:email        - Access user email addresses"
    echo ""
    echo -e "     ${YELLOW}Optional scopes (for full functionality):${NC}"
    echo "     [x] gist              - Create and manage gists"
    echo "     [x] read:project      - Read projects"
    echo "     [x] read:discussion   - Read discussions"
    echo ""
    echo "  6. Click 'Generate token' and copy the token immediately"
    echo "     (You won't be able to see it again!)"
    echo ""
    echo "============================================================"
    echo -e "${YELLOW}Firecrawl API Key (for firecrawl MCP)${NC}"
    echo "============================================================"
    echo ""
    echo "How to get your API key:"
    echo "  1. Go to: https://www.firecrawl.dev/"
    echo "  2. Sign up or log in to your account"
    echo "  3. Navigate to: https://www.firecrawl.dev/app/api-keys"
    echo "  4. Click 'Create API Key'"
    echo "  5. Copy the generated API key"
    echo ""
    echo "  Note: Firecrawl offers a free tier with limited requests."
    echo "        Check pricing at: https://www.firecrawl.dev/pricing"
    echo ""
    echo "============================================================"
    echo -e "${YELLOW}Context7 API Key (for context7 MCP) [Optional]${NC}"
    echo "============================================================"
    echo ""
    echo "How to get your API key:"
    echo "  1. Go to: https://context7.com/"
    echo "  2. Sign up or log in to your account"
    echo "  3. Navigate to Dashboard -> API Keys"
    echo "  4. Click 'Create API Key'"
    echo "  5. Copy the generated API key (starts with 'ctx7sk-')"
    echo ""
    echo "  Note: Context7 works without API key but with rate limits."
    echo "        API key provides higher quotas and priority access."
    echo "        This is OPTIONAL - you can skip if you don't have one."
    echo ""
    echo "============================================================"
    echo ""

    # Initialize env content
    ENV_CONTENT=""
    ENV_UPDATED=false

    # Load existing env if present
    if [ -f "$GEMINI_ENV_PATH" ]; then
        source "$GEMINI_ENV_PATH" 2>/dev/null || true
    fi

    # Ask for GitHub token
    if [ -n "$GITHUB_PERSONAL_ACCESS_TOKEN" ]; then
        write_success "GITHUB_PERSONAL_ACCESS_TOKEN already set"
        read -p "Update it? (y/N): " UPDATE_GITHUB
        if [ "$UPDATE_GITHUB" = "y" ] || [ "$UPDATE_GITHUB" = "Y" ]; then
            read -s -p "Enter your GitHub Personal Access Token: " NEW_GITHUB_TOKEN
            echo
            if [ -n "$NEW_GITHUB_TOKEN" ]; then
                GITHUB_PERSONAL_ACCESS_TOKEN="$NEW_GITHUB_TOKEN"
                ENV_UPDATED=true
            fi
        fi
    else
        read -p "Configure GITHUB_PERSONAL_ACCESS_TOKEN now? (Y/n): " CONFIG_GITHUB
        if [ "$CONFIG_GITHUB" != "n" ] && [ "$CONFIG_GITHUB" != "N" ]; then
            read -s -p "Enter your GitHub Personal Access Token: " GITHUB_PERSONAL_ACCESS_TOKEN
            echo
            if [ -n "$GITHUB_PERSONAL_ACCESS_TOKEN" ]; then
                ENV_UPDATED=true
                write_success "GitHub token configured"
            else
                write_warning "Skipped GitHub token (github MCP will not work)"
            fi
        else
            write_warning "Skipped GitHub token (github MCP will not work)"
        fi
    fi

    # Ask for Firecrawl API key
    if [ -n "$FIRECRAWL_API_KEY" ]; then
        write_success "FIRECRAWL_API_KEY already set"
        read -p "Update it? (y/N): " UPDATE_FIRECRAWL
        if [ "$UPDATE_FIRECRAWL" = "y" ] || [ "$UPDATE_FIRECRAWL" = "Y" ]; then
            read -s -p "Enter your Firecrawl API Key: " NEW_FIRECRAWL_KEY
            echo
            if [ -n "$NEW_FIRECRAWL_KEY" ]; then
                FIRECRAWL_API_KEY="$NEW_FIRECRAWL_KEY"
                ENV_UPDATED=true
            fi
        fi
    else
        read -p "Configure FIRECRAWL_API_KEY now? (Y/n): " CONFIG_FIRECRAWL
        if [ "$CONFIG_FIRECRAWL" != "n" ] && [ "$CONFIG_FIRECRAWL" != "N" ]; then
            read -s -p "Enter your Firecrawl API Key: " FIRECRAWL_API_KEY
            echo
            if [ -n "$FIRECRAWL_API_KEY" ]; then
                ENV_UPDATED=true
                write_success "Firecrawl API key configured"
            else
                write_warning "Skipped Firecrawl API key (firecrawl MCP will not work)"
            fi
        else
            write_warning "Skipped Firecrawl API key (firecrawl MCP will not work)"
        fi
    fi

    # Ask for Context7 API key (optional)
    if [ -n "$CONTEXT7_API_KEY" ]; then
        write_success "CONTEXT7_API_KEY already set"
        read -p "Update it? (y/N): " UPDATE_CONTEXT7
        if [ "$UPDATE_CONTEXT7" = "y" ] || [ "$UPDATE_CONTEXT7" = "Y" ]; then
            read -s -p "Enter your Context7 API Key: " NEW_CONTEXT7_KEY
            echo
            if [ -n "$NEW_CONTEXT7_KEY" ]; then
                CONTEXT7_API_KEY="$NEW_CONTEXT7_KEY"
                ENV_UPDATED=true
            fi
        fi
    else
        read -p "Configure CONTEXT7_API_KEY now? (optional, press Enter to skip): " CONFIG_CONTEXT7
        if [ "$CONFIG_CONTEXT7" = "y" ] || [ "$CONFIG_CONTEXT7" = "Y" ]; then
            read -s -p "Enter your Context7 API Key: " CONTEXT7_API_KEY
            echo
            if [ -n "$CONTEXT7_API_KEY" ]; then
                ENV_UPDATED=true
                write_success "Context7 API key configured"
            else
                write_warning "Skipped Context7 API key (context7 will work with rate limits)"
            fi
        else
            write_warning "Skipped Context7 API key (context7 will work with rate limits)"
        fi
    fi

    # Write env file if we have any tokens
    if [ -n "$GITHUB_PERSONAL_ACCESS_TOKEN" ] || [ -n "$FIRECRAWL_API_KEY" ] || [ -n "$CONTEXT7_API_KEY" ]; then
        cat > "$GEMINI_ENV_PATH" << EOF
# Gemini CLI MCP API Keys
# Auto-generated by OMCC setup script
# Add 'source ~/.gemini/.env' to your shell profile to load these automatically

EOF
        if [ -n "$GITHUB_PERSONAL_ACCESS_TOKEN" ]; then
            echo "export GITHUB_PERSONAL_ACCESS_TOKEN=\"$GITHUB_PERSONAL_ACCESS_TOKEN\"" >> "$GEMINI_ENV_PATH"
        fi
        if [ -n "$FIRECRAWL_API_KEY" ]; then
            echo "export FIRECRAWL_API_KEY=\"$FIRECRAWL_API_KEY\"" >> "$GEMINI_ENV_PATH"
        fi
        if [ -n "$CONTEXT7_API_KEY" ]; then
            echo "export CONTEXT7_API_KEY=\"$CONTEXT7_API_KEY\"" >> "$GEMINI_ENV_PATH"
        fi
        chmod 600 "$GEMINI_ENV_PATH"
        write_success "API keys saved to $GEMINI_ENV_PATH"

        # Detect shell and suggest adding source command
        SHELL_NAME=$(basename "$SHELL")
        case "$SHELL_NAME" in
            bash)
                SHELL_RC="$HOME/.bashrc"
                ;;
            zsh)
                SHELL_RC="$HOME/.zshrc"
                ;;
            fish)
                SHELL_RC="$HOME/.config/fish/config.fish"
                ;;
            *)
                SHELL_RC="$HOME/.profile"
                ;;
        esac

        # Check if source command already exists
        if [ -f "$SHELL_RC" ] && grep -q "source.*\.gemini/.env" "$SHELL_RC" 2>/dev/null; then
            write_success "Shell profile already configured to load Gemini env"
        else
            echo ""
            read -p "Add 'source ~/.gemini/.env' to $SHELL_RC? (Y/n): " ADD_SOURCE
            if [ "$ADD_SOURCE" != "n" ] && [ "$ADD_SOURCE" != "N" ]; then
                echo "" >> "$SHELL_RC"
                echo "# OMCC: Load Gemini CLI API keys" >> "$SHELL_RC"
                echo "[ -f ~/.gemini/.env ] && source ~/.gemini/.env" >> "$SHELL_RC"
                write_success "Added source command to $SHELL_RC"
                write_warning "Run 'source $SHELL_RC' or restart your terminal to apply"
            else
                write_warning "Remember to run 'source ~/.gemini/.env' before using Gemini CLI"
            fi
        fi
    fi

    # =========================================================================
    # Step 6.3: Install UI/UX Pro Max skill (optional)
    # =========================================================================
    echo ""
    echo -e "${CYAN}  Installing UI/UX Pro Max skill (optional)...${NC}"

    if command -v npm &> /dev/null; then
        # Check if uipro is already installed
        if command -v uipro &> /dev/null; then
            write_success "uipro-cli is already installed"
        else
            write_warning "Installing UI/UX Pro Max skill for Frontend agent..."
            set +e
            npm install -g uipro-cli 2>/dev/null
            NPM_EXIT=$?
            set -e
            if [ $NPM_EXIT -eq 0 ]; then
                write_success "Installed uipro-cli"
            else
                write_warning "Failed to install uipro-cli (optional)"
            fi
        fi

        # Initialize uipro for gemini if installed
        if command -v uipro &> /dev/null; then
            set +e
            uipro init --ai gemini 2>/dev/null
            UIPRO_EXIT=$?
            set -e
            if [ $UIPRO_EXIT -eq 0 ]; then
                write_success "Initialized UI/UX Pro Max for Gemini"
            else
                write_warning "Failed to initialize uipro for Gemini (may already be initialized)"
            fi
        fi
    else
        write_warning "npm not found, skipping UI/UX Pro Max skill installation"
        write_warning "To install manually: npm install -g uipro-cli && uipro init --ai gemini"
    fi
else
    write_warning "gemini CLI not installed, skipping Gemini configuration"
    write_warning "Frontend/Librarian/Looker agents require Gemini CLI"
    write_warning "Install: https://github.com/google-gemini/gemini-cli"
fi

# ==============================================================================
# Step 7: Configure Coder
# ==============================================================================
write_step "Step 7: Configuring Coder..."

CONFIG_DIR="$HOME/.omcc-mcp"
CONFIG_PATH="$CONFIG_DIR/config.toml"

# Create config directory if it doesn't exist
mkdir -p "$CONFIG_DIR"

# Check if config already exists
if [ -f "$CONFIG_PATH" ]; then
    write_warning "Config file already exists at $CONFIG_PATH"
    read -p "Overwrite? (y/N): " OVERWRITE
    if [ "$OVERWRITE" != "y" ] && [ "$OVERWRITE" != "Y" ]; then
        write_warning "Skipping Coder configuration"
        # Jump to Done
        echo ""
        echo -e "${GREEN}============================================================${NC}"
        write_success "OMCC setup completed successfully!"
        echo -e "${GREEN}============================================================${NC}"
        echo ""
        echo "Next steps:"
        echo "  1. Restart Claude Code CLI"
        echo "  2. Verify MCP server: claude mcp list"
        echo "  3. Check available skills: /omcc-workflow"
        echo ""
        exit 0
    fi
fi

# Prompt for API Token (hidden input)
read -s -p "Enter your API Token: " API_TOKEN
echo
if [ -z "$API_TOKEN" ]; then
    write_error "API Token is required"
    exit 1
fi

# Prompt for Base URL (optional)
read -p "Enter Base URL (default: https://open.bigmodel.cn/api/anthropic): " BASE_URL
if [ -z "$BASE_URL" ]; then
    BASE_URL="https://open.bigmodel.cn/api/anthropic"
fi

# Prompt for Model (optional)
read -p "Enter Model (default: glm-4.7): " MODEL
if [ -z "$MODEL" ]; then
    MODEL="glm-4.7"
fi

# Escape special characters for TOML string values (backslash and double quote)
SAFE_API_TOKEN=$(printf '%s' "$API_TOKEN" | sed 's/\\/\\\\/g; s/"/\\"/g')
SAFE_BASE_URL=$(printf '%s' "$BASE_URL" | sed 's/\\/\\\\/g; s/"/\\"/g')
SAFE_MODEL=$(printf '%s' "$MODEL" | sed 's/\\/\\\\/g; s/"/\\"/g')

# Generate config.toml
cat > "$CONFIG_PATH" << EOF
[coder]
api_token = "$SAFE_API_TOKEN"
base_url = "$SAFE_BASE_URL"
model = "$SAFE_MODEL"

[coder.env]
CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC = "1"
EOF

# Set file permissions - only current user can read/write
chmod 600 "$CONFIG_PATH"

write_success "Coder configuration saved to $CONFIG_PATH"

# ==============================================================================
# Done!
# ==============================================================================
echo ""
echo -e "${GREEN}============================================================${NC}"
write_success "OMCC setup completed successfully!"
echo -e "${GREEN}============================================================${NC}"
echo ""

echo "Next steps:"
echo "  1. Restart Claude Code CLI"
echo "  2. Verify MCP server: claude mcp list"
echo "  3. Check available skills: /omcc-workflow"
echo ""
