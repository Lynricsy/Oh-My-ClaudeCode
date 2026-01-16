# OMCC One-Click Setup Script for Windows
# This script automates the setup of Coder-Codex-Gemini MCP server

param(
    [switch]$WhatIf,
    [switch]$Help
)

# Show help
if ($Help) {
    Write-Host @"
OMCC One-Click Setup Script for Windows

Usage: .\setup.ps1 [-WhatIf] [-Help]

Options:
  -WhatIf    Dry-run mode. Show what would be done without making changes.
  -Help      Show this help message.

Examples:
  .\setup.ps1           # Run the setup
  .\setup.ps1 -WhatIf   # Preview what would be done
"@
    exit 0
}

$DryRun = $WhatIf.IsPresent

# Force UTF-8 encoding for file operations
$PSDefaultParameterValues['Out-File:Encoding'] = 'utf8'
$PSDefaultParameterValues['Set-Content:Encoding'] = 'utf8'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

function Write-Step {
    param([string]$Message)
    Write-Host "`n[*] $Message" -ForegroundColor Cyan
}

function Write-Success {
    param([string]$Message)
    Write-Host "[OK] $Message" -ForegroundColor Green
}

function Write-ErrorMsg {
    param([string]$Message)
    Write-Host "[ERROR] $Message" -ForegroundColor Red
}

function Write-WarningMsg {
    param([string]$Message)
    Write-Host "[WARN] $Message" -ForegroundColor Yellow
}

function Write-DryRun {
    param([string]$Message)
    Write-Host "[DRY-RUN] $Message" -ForegroundColor Magenta
}

# ==============================================================================
# Dry-run mode banner
# ==============================================================================
if ($DryRun) {
    Write-Host "`n============================================================" -ForegroundColor Magenta
    Write-Host "  DRY-RUN MODE - No changes will be made" -ForegroundColor Magenta
    Write-Host "============================================================`n" -ForegroundColor Magenta
}

# ==============================================================================
# Step 1: Check dependencies
# ==============================================================================
Write-Step "Step 1: Checking dependencies..."

# Helper function to refresh PATH by merging registry PATH with current session PATH
function Refresh-PathFromRegistry {
    $registryPath = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
    $currentPath = $env:Path
    # Merge: add registry paths that are not already in current PATH
    $currentPaths = $currentPath -split ';' | Where-Object { $_ -ne '' }
    $registryPaths = $registryPath -split ';' | Where-Object { $_ -ne '' }
    $newPaths = $registryPaths | Where-Object { $_ -notin $currentPaths }
    if ($newPaths) {
        $env:Path = $currentPath + ";" + ($newPaths -join ';')
    }
}

# Check uv
$uvInstalled = $false
try {
    $null = uv --version 2>&1
    $uvInstalled = $true
    Write-Success "uv is installed"
} catch {
    # Try refreshing PATH from registry (may help find tools installed by npm, scoop, etc.)
    Refresh-PathFromRegistry
    try {
        $null = uv --version 2>&1
        $uvInstalled = $true
        Write-Success "uv is installed"
    } catch {
        if ($DryRun) {
            Write-WarningMsg "uv is not installed"
            Write-DryRun "Would install uv automatically"
        } else {
            Write-WarningMsg "uv is not installed, installing automatically..."
            try {
                powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
                # Refresh PATH again after installation
                Refresh-PathFromRegistry
                $null = uv --version 2>&1
                $uvInstalled = $true
                Write-Success "uv installed successfully"
            } catch {
                Write-ErrorMsg "Failed to install uv automatically"
                Write-Host "Please install uv manually: https://github.com/astral-sh/uv" -ForegroundColor Yellow
                exit 1
            }
        }
    }
}

# Check claude CLI
$claudeInstalled = $false
try {
    $null = claude --version 2>&1
    $claudeInstalled = $true
    Write-Success "claude CLI is installed"
} catch {
    # Try refreshing PATH from registry (may help find tools installed by npm, scoop, etc.)
    Refresh-PathFromRegistry
    try {
        $null = claude --version 2>&1
        $claudeInstalled = $true
        Write-Success "claude CLI is installed"
    } catch {
        if ($DryRun) {
            Write-WarningMsg "claude CLI is not installed"
            Write-DryRun "Would require claude CLI to be installed before running"
        } else {
            Write-ErrorMsg "claude CLI is not installed"
            Write-Host "Please install Claude Code CLI first: https://docs.anthropic.com/en/docs/claude-code" -ForegroundColor Yellow
            Write-Host ""
            Write-Host "If you have already installed claude CLI, please check:" -ForegroundColor Yellow
            Write-Host "  1. Restart your terminal to refresh PATH" -ForegroundColor White
            Write-Host "  2. Ensure claude is in your PATH: where.exe claude" -ForegroundColor White
            Write-Host "  3. For npm install: npm install -g @anthropic-ai/claude-code" -ForegroundColor White
            exit 1
        }
    }
}

# ==============================================================================
# Step 2: Install project dependencies
# ==============================================================================
Write-Step "Step 2: Installing project dependencies..."

if ($DryRun) {
    Write-DryRun "Would run: uv sync"
    Write-Success "Project dependencies would be installed"
} else {
    uv sync
    if ($LASTEXITCODE -ne 0) {
        Write-ErrorMsg "Failed to install dependencies"
        exit 1
    }
    Write-Success "Project dependencies installed"
}

# ==============================================================================
# Step 3: Register MCP server
# ==============================================================================
Write-Step "Step 3: Registering MCP server..."

if ($DryRun) {
    Write-DryRun "Would run: claude mcp remove omcc --scope user"

    # Check uv version
    $useRefresh = $false
    try {
        $uvVersionOutput = uv --version 2>&1
        if ($uvVersionOutput -match "uv (\d+)\.(\d+)\.(\d+)") {
            $major = [int]$Matches[1]
            $minor = [int]$Matches[2]
            if ($major -gt 0 -or ($major -eq 0 -and $minor -ge 4)) {
                $useRefresh = $true
            }
        }
    } catch {}

    if ($useRefresh) {
        Write-DryRun "Would run: claude mcp add omcc --scope user --transport stdio -- uvx --refresh --from git+https://github.com/Lynricsy/Oh-My-ClaudeCode.git omcc-mcp"
    } else {
        Write-DryRun "Would run: claude mcp add omcc --scope user --transport stdio -- uvx --from git+https://github.com/Lynricsy/Oh-My-ClaudeCode.git omcc-mcp"
    }
    Write-Success "MCP server would be registered"
} else {
    # Temporarily relax error handling for native commands in Step 3
    $oldErrorActionPreference = $ErrorActionPreference
    $oldNativeCommandEap = $null
    $ErrorActionPreference = "Continue"
    if ($PSVersionTable.PSVersion.Major -ge 7) {
        $oldNativeCommandEap = $PSNativeCommandUseErrorActionPreference
        $PSNativeCommandUseErrorActionPreference = $false
    }

    try {
        # Try to remove existing omcc MCP server if it exists
        $null = & claude @("mcp","remove","omcc","--scope","user") 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-WarningMsg "Removed existing omcc MCP server"
        }

        # Check uv version to determine if --refresh is supported
        $mcpRegistered = $false
        $lastError = ""
        $useRefresh = $false
        $uvVersionKnown = $false

        try {
            $uvVersionOutput = uv --version 2>&1
            if ($uvVersionOutput -match "uv (\d+)\.(\d+)\.(\d+)") {
                $uvVersionKnown = $true
                $major = [int]$Matches[1]
                $minor = [int]$Matches[2]
                # --refresh requires uv >= 0.4.0
                if ($major -gt 0 -or ($major -eq 0 -and $minor -ge 4)) {
                    $useRefresh = $true
                }
            }
        } catch {
            # If we can't determine version, don't use --refresh
        }

        if ($useRefresh) {
            # Try with --refresh first
            $refreshSucceeded = $false
            try {
                $refreshOutput = & claude @("mcp","add","omcc","--scope","user","--transport","stdio","--","uvx","--refresh","--from","git+https://github.com/Lynricsy/Oh-My-ClaudeCode.git","omcc-mcp") 2>&1
                if ($LASTEXITCODE -eq 0) {
                    $refreshSucceeded = $true
                }
            } catch {
                $refreshOutput = $_.Exception.Message
                $refreshSucceeded = $false
            }

            if ($refreshSucceeded) {
                $mcpRegistered = $true
                Write-Success "MCP server registered (with --refresh)"
            } else {
                # Check if error is about --refresh option (covers various CLI error message formats)
                # Use -replace to normalize whitespace for reliable matching
                $refreshOutputStr = ($refreshOutput | Out-String) -replace '\s+', ' '
                if ($refreshOutputStr -match "(?i)(unknown|unrecognized|unexpected|invalid|no such|unsupported|found argument).*--refresh|--refresh.*(unknown|unrecognized|unexpected|invalid|no such|unsupported|found argument)|unknown option.*--refresh") {
                    # Fallback: --refresh was rejected, try without it
                    Write-WarningMsg "--refresh option was rejected, falling back to installation without --refresh..."
                    $fallbackSucceeded = $false
                    try {
                        $fallbackOutput = & claude @("mcp","add","omcc","--scope","user","--transport","stdio","--","uvx","--from","git+https://github.com/Lynricsy/Oh-My-ClaudeCode.git","omcc-mcp") 2>&1
                        if ($LASTEXITCODE -eq 0) {
                            $fallbackSucceeded = $true
                        }
                    } catch {
                        $fallbackOutput = $_.Exception.Message
                        $fallbackSucceeded = $false
                    }
                    if ($fallbackSucceeded) {
                        $mcpRegistered = $true
                        Write-Success "MCP server registered (without --refresh)"
                    } else {
                        $lastError = $fallbackOutput
                    }
                } else {
                    $lastError = $refreshOutput
                }
            }
        } else {
            # uv version too old or unknown, skip --refresh
            if ($uvVersionKnown) {
                Write-WarningMsg "Your uv version does not support --refresh option (requires uv >= 0.4.0)"
            } else {
                Write-WarningMsg "Could not determine uv version, skipping --refresh option"
            }
            Write-WarningMsg "Installing without --refresh..."
            Write-WarningMsg "Consider upgrading uv: powershell -c `"irm https://astral.sh/uv/install.ps1 | iex`""

            $fallbackSucceeded = $false
            try {
                $fallbackOutput = & claude @("mcp","add","omcc","--scope","user","--transport","stdio","--","uvx","--from","git+https://github.com/Lynricsy/Oh-My-ClaudeCode.git","omcc-mcp") 2>&1
                if ($LASTEXITCODE -eq 0) {
                    $fallbackSucceeded = $true
                }
            } catch {
                $fallbackOutput = $_.Exception.Message
                $fallbackSucceeded = $false
            }
            if ($fallbackSucceeded) {
                $mcpRegistered = $true
                Write-Success "MCP server registered (without --refresh)"
            } else {
                $lastError = $fallbackOutput
            }
        }

        if (-not $mcpRegistered) {
            Write-ErrorMsg "Failed to register MCP server"
            Write-Host "Error details: $lastError" -ForegroundColor Red
            exit 1
        }
    } finally {
        $ErrorActionPreference = $oldErrorActionPreference
        if ($PSVersionTable.PSVersion.Major -ge 7) {
            $PSNativeCommandUseErrorActionPreference = $oldNativeCommandEap
        }
    }
}

# ==============================================================================
# Step 4: Install Skills
# ==============================================================================
Write-Step "Step 4: Installing Skills..."

$skillsDir = "$env:USERPROFILE\.claude\skills"

# List of all skills to install
$skills = @("omcc-workflow", "gemini-collaboration", "frontend", "chore", "librarian", "looker")

if ($DryRun) {
    if (!(Test-Path $skillsDir)) {
        Write-DryRun "Would create directory: $skillsDir"
    }
    foreach ($skill in $skills) {
        $source = Join-Path $PSScriptRoot "skills\$skill"
        if (Test-Path $source) {
            Write-DryRun "Would copy: $source -> $skillsDir\$skill"
            Write-Success "$skill skill would be installed"
        } else {
            Write-WarningMsg "$skill skill not found, would skip"
        }
    }
} else {
    try {
        # Create skills directory if it doesn't exist
        if (!(Test-Path $skillsDir)) {
            New-Item -ItemType Directory -Path $skillsDir -Force | Out-Null
            Write-Success "Created skills directory: $skillsDir"
        }

        # Install each skill
        foreach ($skill in $skills) {
            $source = Join-Path $PSScriptRoot "skills\$skill"
            if (Test-Path $source) {
                $dest = "$skillsDir\$skill"
                if (Test-Path $dest) {
                    Remove-Item -Recurse -Force $dest
                }
                Copy-Item -Recurse $source $dest
                Write-Success "Installed $skill skill"
            } else {
                Write-WarningMsg "$skill skill not found, skipping"
            }
        }
    } catch {
        Write-ErrorMsg "Failed to install skills"
        exit 1
    }
}

# ==============================================================================
# Step 5: Configure global CLAUDE.md
# ==============================================================================
Write-Step "Step 5: Configuring global CLAUDE.md..."

$claudeMdPath = "$env:USERPROFILE\.claude\CLAUDE.md"
$omccMarker = "# OMCC Configuration"

# Read OMCC config from external file to avoid encoding issues
$omccConfigPath = Join-Path $PSScriptRoot "templates\omcc-global-prompt.md"

if ($DryRun) {
    if (!(Test-Path $claudeMdPath)) {
        if (Test-Path $omccConfigPath) {
            Write-DryRun "Would create: $claudeMdPath (from template)"
            Write-Success "Global CLAUDE.md would be created"
        } else {
            Write-WarningMsg "OMCC global prompt template not found at $omccConfigPath"
        }
    } else {
        $content = Get-Content $claudeMdPath -Raw -Encoding UTF8
        if ($content -match [regex]::Escape($omccMarker)) {
            Write-WarningMsg "OMCC configuration already exists in CLAUDE.md, would skip"
        } else {
            if (Test-Path $omccConfigPath) {
                Write-DryRun "Would append OMCC configuration to: $claudeMdPath"
                Write-Success "OMCC configuration would be appended to CLAUDE.md"
            } else {
                Write-WarningMsg "OMCC global prompt template not found at $omccConfigPath"
            }
        }
    }
} else {
    try {
        if (!(Test-Path $claudeMdPath)) {
            # Create new file with OMCC config
            if (Test-Path $omccConfigPath) {
                Copy-Item $omccConfigPath $claudeMdPath
                Write-Success "Created global CLAUDE.md"
            } else {
                Write-WarningMsg "OMCC global prompt template not found at $omccConfigPath"
                Write-WarningMsg "Please manually copy the OMCC configuration to $claudeMdPath"
            }
        } else {
            # Check if OMCC config already exists
            $content = Get-Content $claudeMdPath -Raw -Encoding UTF8
            if ($content -match [regex]::Escape($omccMarker)) {
                Write-WarningMsg "OMCC configuration already exists in CLAUDE.md, skipping"
            } else {
                # Append OMCC config
                if (Test-Path $omccConfigPath) {
                    $omccContent = Get-Content $omccConfigPath -Raw -Encoding UTF8
                    Add-Content -Path $claudeMdPath -Value "`n$omccContent" -Encoding UTF8
                    Write-Success "Appended OMCC configuration to CLAUDE.md"
                } else {
                    Write-WarningMsg "OMCC global prompt template not found at $omccConfigPath"
                    Write-WarningMsg "Please manually copy the OMCC configuration to $claudeMdPath"
                }
            }
        }
    } catch {
        Write-ErrorMsg "Failed to configure global CLAUDE.md: $_"
        exit 1
    }
}

# ==============================================================================
# Step 6: Configure Gemini CLI (for Frontend/Librarian/Looker)
# ==============================================================================
Write-Step "Step 6: Configuring Gemini CLI..."

$geminiDir = "$env:USERPROFILE\.gemini"
$geminiSettingsSource = Join-Path $PSScriptRoot "templates\gemini\settings.json"
$geminiSettingsPath = "$geminiDir\settings.json"
$geminiEnvPath = "$geminiDir\.env.ps1"

if ($DryRun) {
    # Check if gemini CLI is available
    try {
        $null = Get-Command gemini -ErrorAction Stop
        Write-Success "gemini CLI is installed"

        if (!(Test-Path $geminiDir)) {
            Write-DryRun "Would create directory: $geminiDir"
        }
        if (Test-Path $geminiSettingsSource) {
            if (Test-Path $geminiSettingsPath) {
                Write-WarningMsg "Gemini settings.json already exists, would skip"
            } else {
                Write-DryRun "Would copy: $geminiSettingsSource -> $geminiSettingsPath"
                Write-Success "Gemini settings.json would be installed"
            }
        }

        Write-DryRun "Would check Docker availability for github MCP"
        Write-DryRun "Would check npx availability for firecrawl MCP"
        Write-DryRun "Would prompt for: GITHUB_PERSONAL_ACCESS_TOKEN, FIRECRAWL_API_KEY"
        Write-DryRun "Would create env file: $geminiEnvPath"

        try {
            $null = Get-Command npm -ErrorAction Stop
            Write-DryRun "Would install uipro-cli: npm install -g uipro-cli"
            Write-DryRun "Would initialize UI/UX Pro Max: uipro init --ai gemini"
        } catch {
            Write-WarningMsg "npm not found, would skip UI/UX Pro Max installation"
        }
    } catch {
        Write-WarningMsg "gemini CLI not installed, would skip Gemini configuration"
    }
} else {
    # Check if gemini CLI is available
    $geminiInstalled = $false
    try {
        $null = Get-Command gemini -ErrorAction Stop
        $geminiInstalled = $true
        Write-Success "gemini CLI is installed"
    } catch {
        Write-WarningMsg "gemini CLI not installed, skipping Gemini configuration"
        Write-WarningMsg "Frontend/Librarian/Looker agents require Gemini CLI"
        Write-WarningMsg "Install: https://github.com/google-gemini/gemini-cli"
    }

    if ($geminiInstalled) {
        try {
            # Create .gemini directory if it doesn't exist
            if (!(Test-Path $geminiDir)) {
                New-Item -ItemType Directory -Path $geminiDir -Force | Out-Null
            }

            # Copy settings.json if source exists
            if (Test-Path $geminiSettingsSource) {
                if (Test-Path $geminiSettingsPath) {
                    Write-WarningMsg "Gemini settings.json already exists, skipping"
                    Write-WarningMsg "To update, manually merge: $geminiSettingsSource"
                } else {
                    Copy-Item $geminiSettingsSource $geminiSettingsPath
                    Write-Success "Installed Gemini settings.json"
                }
            }

            # =================================================================
            # Step 6.1: Check MCP dependencies
            # =================================================================
            Write-Host ""
            Write-Host "  Checking MCP dependencies..." -ForegroundColor Cyan

            # Check Docker (required for github MCP)
            $dockerAvailable = $false
            try {
                $null = Get-Command docker -ErrorAction Stop
                # Check if Docker daemon is running
                $dockerInfo = docker info 2>&1
                if ($LASTEXITCODE -eq 0) {
                    $dockerAvailable = $true
                    Write-Success "Docker is installed and running (required for github MCP)"
                } else {
                    Write-WarningMsg "Docker is installed but not running"
                    Write-WarningMsg "Start Docker Desktop to enable github MCP"
                }
            } catch {
                Write-WarningMsg "Docker not installed (required for github MCP)"
                Write-WarningMsg "Install Docker: https://docs.docker.com/get-docker/"
            }

            # Check npm/npx (required for firecrawl MCP)
            $npxAvailable = $false
            try {
                $null = Get-Command npx -ErrorAction Stop
                $npxAvailable = $true
                Write-Success "npx is available (required for firecrawl MCP)"
            } catch {
                Write-WarningMsg "npx not found (required for firecrawl MCP)"
                Write-WarningMsg "Install Node.js: https://nodejs.org/"
            }

            # =================================================================
            # Step 6.2: Configure API keys for MCP servers
            # =================================================================
            Write-Host ""
            Write-Host "  Configuring API keys for MCP servers..." -ForegroundColor Cyan
            Write-Host ""
            Write-Host "============================================================" -ForegroundColor White
            Write-Host "GitHub Personal Access Token (for github MCP)" -ForegroundColor Yellow
            Write-Host "============================================================" -ForegroundColor White
            Write-Host ""
            Write-Host "How to get your token:"
            Write-Host "  1. Go to: https://github.com/settings/tokens"
            Write-Host "  2. Click 'Generate new token' -> 'Generate new token (classic)'"
            Write-Host "  3. Set a descriptive name (e.g., 'OMCC Gemini MCP')"
            Write-Host "  4. Set expiration as needed (recommend: 90 days or No expiration)"
            Write-Host "  5. Select the following scopes:"
            Write-Host ""
            Write-Host "     Required scopes:" -ForegroundColor Green
            Write-Host "     [x] repo              - Full control of private repositories"
            Write-Host "         [x] repo:status   - Access commit status"
            Write-Host "         [x] repo_deployment - Access deployment status"
            Write-Host "         [x] public_repo   - Access public repositories"
            Write-Host "         [x] repo:invite   - Access repository invitations"
            Write-Host "     [x] read:org          - Read org and team membership"
            Write-Host "     [x] read:user         - Read user profile data"
            Write-Host "     [x] user:email        - Access user email addresses"
            Write-Host ""
            Write-Host "     Optional scopes (for full functionality):" -ForegroundColor Yellow
            Write-Host "     [x] gist              - Create and manage gists"
            Write-Host "     [x] read:project      - Read projects"
            Write-Host "     [x] read:discussion   - Read discussions"
            Write-Host ""
            Write-Host "  6. Click 'Generate token' and copy the token immediately"
            Write-Host "     (You won't be able to see it again!)"
            Write-Host ""
            Write-Host "============================================================" -ForegroundColor White
            Write-Host "Firecrawl API Key (for firecrawl MCP)" -ForegroundColor Yellow
            Write-Host "============================================================" -ForegroundColor White
            Write-Host ""
            Write-Host "How to get your API key:"
            Write-Host "  1. Go to: https://www.firecrawl.dev/"
            Write-Host "  2. Sign up or log in to your account"
            Write-Host "  3. Navigate to: https://www.firecrawl.dev/app/api-keys"
            Write-Host "  4. Click 'Create API Key'"
            Write-Host "  5. Copy the generated API key"
            Write-Host ""
            Write-Host "  Note: Firecrawl offers a free tier with limited requests."
            Write-Host "        Check pricing at: https://www.firecrawl.dev/pricing"
            Write-Host ""
            Write-Host "============================================================" -ForegroundColor White
            Write-Host ""

            # Load existing env if present
            $githubToken = $env:GITHUB_PERSONAL_ACCESS_TOKEN
            $firecrawlKey = $env:FIRECRAWL_API_KEY
            if (Test-Path $geminiEnvPath) {
                . $geminiEnvPath 2>$null
                if ($env:GITHUB_PERSONAL_ACCESS_TOKEN) { $githubToken = $env:GITHUB_PERSONAL_ACCESS_TOKEN }
                if ($env:FIRECRAWL_API_KEY) { $firecrawlKey = $env:FIRECRAWL_API_KEY }
            }

            $envUpdated = $false

            # Ask for GitHub token
            if ($githubToken) {
                Write-Success "GITHUB_PERSONAL_ACCESS_TOKEN already set"
                $updateGithub = Read-Host "Update it? (y/N)"
                if ($updateGithub -eq "y" -or $updateGithub -eq "Y") {
                    $secureToken = Read-Host "Enter your GitHub Personal Access Token" -AsSecureString
                    $githubToken = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureToken))
                    if ($githubToken) {
                        $envUpdated = $true
                    }
                }
            } else {
                $configGithub = Read-Host "Configure GITHUB_PERSONAL_ACCESS_TOKEN now? (Y/n)"
                if ($configGithub -ne "n" -and $configGithub -ne "N") {
                    $secureToken = Read-Host "Enter your GitHub Personal Access Token" -AsSecureString
                    $githubToken = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureToken))
                    if ($githubToken) {
                        $envUpdated = $true
                        Write-Success "GitHub token configured"
                    } else {
                        Write-WarningMsg "Skipped GitHub token (github MCP will not work)"
                    }
                } else {
                    Write-WarningMsg "Skipped GitHub token (github MCP will not work)"
                }
            }

            # Ask for Firecrawl API key
            if ($firecrawlKey) {
                Write-Success "FIRECRAWL_API_KEY already set"
                $updateFirecrawl = Read-Host "Update it? (y/N)"
                if ($updateFirecrawl -eq "y" -or $updateFirecrawl -eq "Y") {
                    $secureKey = Read-Host "Enter your Firecrawl API Key" -AsSecureString
                    $firecrawlKey = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey))
                    if ($firecrawlKey) {
                        $envUpdated = $true
                    }
                }
            } else {
                $configFirecrawl = Read-Host "Configure FIRECRAWL_API_KEY now? (Y/n)"
                if ($configFirecrawl -ne "n" -and $configFirecrawl -ne "N") {
                    $secureKey = Read-Host "Enter your Firecrawl API Key" -AsSecureString
                    $firecrawlKey = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey))
                    if ($firecrawlKey) {
                        $envUpdated = $true
                        Write-Success "Firecrawl API key configured"
                    } else {
                        Write-WarningMsg "Skipped Firecrawl API key (firecrawl MCP will not work)"
                    }
                } else {
                    Write-WarningMsg "Skipped Firecrawl API key (firecrawl MCP will not work)"
                }
            }

            # Write env file if we have any tokens
            if ($githubToken -or $firecrawlKey) {
                $envContent = @"
# Gemini CLI MCP API Keys
# Auto-generated by OMCC setup script
# Add this to your PowerShell profile to load automatically:
#   . `$env:USERPROFILE\.gemini\.env.ps1

"@
                if ($githubToken) {
                    $envContent += "`$env:GITHUB_PERSONAL_ACCESS_TOKEN = `"$githubToken`"`n"
                }
                if ($firecrawlKey) {
                    $envContent += "`$env:FIRECRAWL_API_KEY = `"$firecrawlKey`"`n"
                }

                [System.IO.File]::WriteAllText($geminiEnvPath, $envContent, [System.Text.UTF8Encoding]::new($false))

                # Set file permissions - only current user can read/write
                $acl = Get-Acl $geminiEnvPath
                $acl.SetAccessRuleProtection($true, $false)
                $rule = New-Object System.Security.AccessControl.FileSystemAccessRule($env:USERNAME, "FullControl", "Allow")
                $acl.SetAccessRule($rule)
                Set-Acl $geminiEnvPath $acl

                Write-Success "API keys saved to $geminiEnvPath"

                # Check if PowerShell profile exists and suggest adding source command
                $profilePath = $PROFILE.CurrentUserAllHosts
                $profileDir = Split-Path $profilePath -Parent

                if (!(Test-Path $profileDir)) {
                    New-Item -ItemType Directory -Path $profileDir -Force | Out-Null
                }

                if (Test-Path $profilePath) {
                    $profileContent = Get-Content $profilePath -Raw -ErrorAction SilentlyContinue
                    if ($profileContent -match "\.gemini\\\.env\.ps1") {
                        Write-Success "PowerShell profile already configured to load Gemini env"
                    } else {
                        Write-Host ""
                        $addProfile = Read-Host "Add Gemini env loading to PowerShell profile? (Y/n)"
                        if ($addProfile -ne "n" -and $addProfile -ne "N") {
                            Add-Content -Path $profilePath -Value "`n# OMCC: Load Gemini CLI API keys"
                            Add-Content -Path $profilePath -Value "if (Test-Path `"`$env:USERPROFILE\.gemini\.env.ps1`") { . `"`$env:USERPROFILE\.gemini\.env.ps1`" }"
                            Write-Success "Added to PowerShell profile: $profilePath"
                            Write-WarningMsg "Restart PowerShell or run: . `"$profilePath`""
                        } else {
                            Write-WarningMsg "Remember to run: . `"$geminiEnvPath`" before using Gemini CLI"
                        }
                    }
                } else {
                    Write-Host ""
                    $createProfile = Read-Host "Create PowerShell profile with Gemini env loading? (Y/n)"
                    if ($createProfile -ne "n" -and $createProfile -ne "N") {
                        $profileContent = @"
# OMCC: Load Gemini CLI API keys
if (Test-Path "`$env:USERPROFILE\.gemini\.env.ps1") { . "`$env:USERPROFILE\.gemini\.env.ps1" }
"@
                        [System.IO.File]::WriteAllText($profilePath, $profileContent, [System.Text.UTF8Encoding]::new($false))
                        Write-Success "Created PowerShell profile: $profilePath"
                        Write-WarningMsg "Restart PowerShell or run: . `"$profilePath`""
                    } else {
                        Write-WarningMsg "Remember to run: . `"$geminiEnvPath`" before using Gemini CLI"
                    }
                }
            }

            # =================================================================
            # Step 6.3: Install UI/UX Pro Max skill (optional)
            # =================================================================
            Write-Host ""
            Write-Host "  Installing UI/UX Pro Max skill (optional)..." -ForegroundColor Cyan

            $npmInstalled = $false
            try {
                $null = Get-Command npm -ErrorAction Stop
                $npmInstalled = $true
            } catch {
                Write-WarningMsg "npm not found, skipping UI/UX Pro Max skill installation"
                Write-WarningMsg "To install manually: npm install -g uipro-cli && uipro init --ai gemini"
            }

            if ($npmInstalled) {
                # Check if uipro is already installed
                $uiproInstalled = $false
                try {
                    $null = Get-Command uipro -ErrorAction Stop
                    $uiproInstalled = $true
                    Write-Success "uipro-cli is already installed"
                } catch {
                    Write-WarningMsg "Installing UI/UX Pro Max skill for Frontend agent..."
                    try {
                        $null = npm install -g uipro-cli 2>&1
                        $uiproInstalled = $true
                        Write-Success "Installed uipro-cli"
                    } catch {
                        Write-WarningMsg "Failed to install uipro-cli (optional)"
                    }
                }

                # Initialize uipro for gemini if installed
                if ($uiproInstalled) {
                    try {
                        $null = uipro init --ai gemini 2>&1
                        Write-Success "Initialized UI/UX Pro Max for Gemini"
                    } catch {
                        Write-WarningMsg "Failed to initialize uipro for Gemini (may already be initialized)"
                    }
                }
            }
        } catch {
            Write-WarningMsg "Failed to configure Gemini CLI: $_"
        }
    }
}

# ==============================================================================
# Step 7: Configure Coder
# ==============================================================================
Write-Step "Step 7: Configuring Coder..."

$configDir = "$env:USERPROFILE\.omcc-mcp"
$configPath = "$configDir\config.toml"

if ($DryRun) {
    if (!(Test-Path $configDir)) {
        Write-DryRun "Would create directory: $configDir"
    }
    if (Test-Path $configPath) {
        Write-WarningMsg "Config file already exists at $configPath"
        Write-DryRun "Would prompt: Overwrite? (y/N)"
    }
    Write-DryRun "Would prompt for: API Token, Base URL, Model"
    Write-DryRun "Would create config file: $configPath"
    Write-DryRun "Would set file permissions (current user only)"
    Write-Success "Coder configuration would be saved"
} else {
    $skipCoderConfig = $false

    try {
        # Create config directory if it doesn't exist
        if (!(Test-Path $configDir)) {
            New-Item -ItemType Directory -Path $configDir -Force | Out-Null
        }

        # Check if config already exists
        if (Test-Path $configPath) {
            Write-WarningMsg "Config file already exists at $configPath"
            $overwrite = Read-Host "Overwrite? (y/N)"
            if ($overwrite -ne "y" -and $overwrite -ne "Y") {
                Write-WarningMsg "Skipping Coder configuration"
                $skipCoderConfig = $true
            }
        }

        if (-not $skipCoderConfig) {
            # Prompt for API Token
            $apiToken = Read-Host "Enter your API Token"
            if ([string]::IsNullOrWhiteSpace($apiToken)) {
                Write-ErrorMsg "API Token is required"
                exit 1
            }

            # Prompt for Base URL (optional)
            $baseUrl = Read-Host "Enter Base URL (default: https://open.bigmodel.cn/api/anthropic)"
            if ([string]::IsNullOrWhiteSpace($baseUrl)) {
                $baseUrl = "https://open.bigmodel.cn/api/anthropic"
            }

            # Prompt for Model (optional)
            $model = Read-Host "Enter Model (default: glm-4.7)"
            if ([string]::IsNullOrWhiteSpace($model)) {
                $model = "glm-4.7"
            }

            # Escape special characters for TOML string values (backslash and double quote)
            $safeApiToken = $apiToken -replace '\\', '\\' -replace '"', '\"'
            $safeBaseUrl = $baseUrl -replace '\\', '\\' -replace '"', '\"'
            $safeModel = $model -replace '\\', '\\' -replace '"', '\"'

            # Generate config.toml
            $configContent = @"
[coder]
api_token = "$safeApiToken"
base_url = "$safeBaseUrl"
model = "$safeModel"

[coder.env]
CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC = "1"
"@

            # Use UTF8 without BOM - critical for TOML parsers
            # PowerShell 5.x's "Set-Content -Encoding UTF8" writes BOM (EF BB BF) which breaks TOML parsing
            [System.IO.File]::WriteAllText($configPath, $configContent, [System.Text.UTF8Encoding]::new($false))

            # Set file permissions - only current user can read/write
            $acl = Get-Acl $configPath
            $acl.SetAccessRuleProtection($true, $false)
            $rule = New-Object System.Security.AccessControl.FileSystemAccessRule($env:USERNAME, "FullControl", "Allow")
            $acl.SetAccessRule($rule)
            Set-Acl $configPath $acl

            Write-Success "Coder configuration saved to $configPath"
        }

    } catch {
        Write-ErrorMsg "Failed to configure Coder: $_"
        exit 1
    }
}
# ==============================================================================
# Done!
# ==============================================================================
if ($DryRun) {
    Write-Host "`n============================================================" -ForegroundColor Magenta
    Write-Host "  DRY-RUN COMPLETED - No changes were made" -ForegroundColor Magenta
    Write-Host "============================================================`n" -ForegroundColor Magenta
    Write-Host "Run without -WhatIf to apply changes:" -ForegroundColor Cyan
    Write-Host "  .\setup.ps1" -ForegroundColor White
} else {
    Write-Host "`n============================================================" -ForegroundColor Green
    Write-Success "OMCC setup completed successfully!"
    Write-Host "============================================================`n" -ForegroundColor Green

    Write-Host "Next steps:" -ForegroundColor Cyan
    Write-Host "  1. Restart Claude Code CLI" -ForegroundColor White
    Write-Host "  2. Verify MCP server: claude mcp list" -ForegroundColor White
    Write-Host "  3. Check available skills: /omcc-workflow" -ForegroundColor White
}
Write-Host ""
