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

# Parse arguments
UPDATE_MODE=false
HELP_MODE=false

while [[ "$#" -gt 0 ]]; do
    case $1 in
        -u|--update) UPDATE_MODE=true ;;
        -h|--help) HELP_MODE=true ;;
        *) echo "Unknown parameter: $1"; exit 1 ;;
    esac
    shift
done

# Show help
if [ "$HELP_MODE" = true ]; then
    echo "OMCC One-Click Setup Script for macOS/Linux"
    echo ""
    echo "Usage: ./setup.sh [options]"
    echo ""
    echo "Options:"
    echo "  -u, --update    Update mode. Skip interactive configuration,"
    echo "                  only update MCP server, Skills, and CLAUDE.md."
    echo "  -h, --help      Show this help message."
    echo ""
    echo "Examples:"
    echo "  ./setup.sh           # Full installation with configuration"
    echo "  ./setup.sh --update  # Quick update without re-configuration"
    exit 0
fi

# Update mode banner
if [ "$UPDATE_MODE" = true ]; then
    echo -e "\n${CYAN}============================================================${NC}"
    echo -e "${CYAN}  UPDATE MODE - Skipping interactive configuration${NC}"
    echo -e "${CYAN}============================================================${NC}\n"
fi

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
SKILLS=("omcc-workflow" "advisor-collaboration" "frontend" "chore" "librarian" "looker")

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
        if [ "$UPDATE_MODE" = true ]; then
            # In update mode, replace existing OMCC config
            if [ -f "$OMCC_CONFIG_PATH" ]; then
                # Remove old OMCC config (from marker to end of file or next major section)
                # Create temp file with content before OMCC marker
                sed -n "1,/^$OMCC_MARKER/{ /^$OMCC_MARKER/!p }" "$CLAUDE_MD_PATH" > "${CLAUDE_MD_PATH}.tmp"
                # Append new OMCC config
                echo "" >> "${CLAUDE_MD_PATH}.tmp"
                cat "$OMCC_CONFIG_PATH" >> "${CLAUDE_MD_PATH}.tmp"
                mv "${CLAUDE_MD_PATH}.tmp" "$CLAUDE_MD_PATH"
                write_success "Updated OMCC configuration in CLAUDE.md"
            else
                write_warning "OMCC global prompt template not found at $OMCC_CONFIG_PATH"
            fi
        else
            write_warning "OMCC configuration already exists in CLAUDE.md, skipping"
        fi
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
# Step 6: Check OpenCode CLI (for Gemini/Frontend/Librarian/Looker/Chore)
# ==============================================================================
write_step "Step 6: Checking OpenCode CLI..."

# Check if opencode CLI is installed
if command -v opencode &> /dev/null; then
    write_success "opencode CLI is installed"
    write_warning "Gemini/Frontend/Librarian/Looker/Chore agents use OpenCode CLI"
    write_warning "Make sure to configure OpenCode CLI: ~/.config/opencode/opencode.jsonc"
    write_warning "See: https://opencode.ai/docs/config/"
else
    write_warning "opencode CLI not installed"
    write_warning "Gemini/Frontend/Librarian/Looker/Chore agents require OpenCode CLI"
    write_warning "Install: https://opencode.ai/docs/cli/"
fi

# ==============================================================================
# Step 7: Configure Coder (skip in update mode)
# ==============================================================================
if [ "$UPDATE_MODE" = true ]; then
    write_step "Step 7: Skipping Coder configuration (update mode)"
else
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
fi

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
