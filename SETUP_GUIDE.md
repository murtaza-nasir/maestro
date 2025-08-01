# MAESTRO Setup & Configuration Guide

This guide provides a detailed walkthrough of the setup and configuration options available in the MAESTRO web interface.

## First-Time Login

On the first run, a default administrator account is automatically created for you to get started immediately.

-   **Username**: `admin`
-   **Password**: `adminpass123`

It is **highly recommended** that you change the default password immediately after your first login. You can do this from the **Settings -> Profile** tab.

## Settings Panel Overview

The settings panel is the central hub for customizing your MAESTRO instance. It is organized into several tabs:

### 1. Profile

This tab allows you to manage your personal user account.

-   **User Profile**: Update your personal information, such as your name, location, and job title.
-   **Change Password**: Update your password for security. You will need to enter your current password and a new password.

### 2. AI Config

This tab is crucial for configuring the Large Language Models (LLMs) that power MAESTRO's agents. You can choose between a simple, unified setup or an advanced, per-agent configuration.

#### Provider Configuration (Basic Mode)

This is the default view and the simplest way to get started. You configure a single AI provider and its credentials, which will be used for all models.

-   **AI Provider**: Select your preferred service from the dropdown (e.g., OpenRouter, OpenAI, Groq).
-   **API Key**: Enter the API key for your chosen provider.
-   **Base URL**: The endpoint for the provider's API. This is often pre-filled for standard providers.

Once you have entered your credentials, you can use the **Test** button to ensure the connection is working.

#### Model Selection (Basic Mode)

After configuring a provider, you can select the models for each agent type. The dropdowns will be populated with models available from your chosen provider.

-   **Fast Model**: Used for rapid, simple tasks.
-   **Mid Model**: Used for balanced performance.
-   **Intelligent Model**: Used for complex analysis.
-   **Verifier Model**: Used for verification tasks.

#### Advanced Configuration (Advanced Mode)

For more granular control, you can enable **Advanced Mode** by toggling the switch at the top of the page. This mode allows you to configure a separate provider, API key, and model for each agent type individually.

When Advanced Mode is enabled, the UI will display separate configuration boxes for:
-   **Fast Model Configuration**
-   **Mid Model Configuration**
-   **Intelligent Model Configuration**

Within each box, you can independently set the **Provider**, **Model Name**, **API Key**, and **Base URL**.

This mode is ideal for power users who want to optimize for cost and performance by using different LLMs from different providers for specific tasks. For example, you could use a small, fast model from Groq for the "Fast Model" agent and a powerful model like GPT-4o from OpenAI for the "Intelligent Model" agent.

### 3. Search

Configure the web search provider used by the Research Agent.

-   **Search Provider**: Choose your preferred web search service.
    -   **Tavily**
    -   **LinkUp**
    -   **SearXNG** (for self-hosted search)
-   **API Key**: Enter the API key for the selected search provider.

### 4. Research

Fine-tune the default parameters for the research process. These settings can be overridden for individual missions.

-   **AI-Powered Configuration**: Toggle this to allow an AI agent to dynamically optimize the research parameters based on your request.
-   **Research Configuration**:
    -   `Max Depth`: The depth of the research outline.
    -   `Max Questions`: The number of questions to generate for the research plan.
    -   `Research Rounds`: The number of iterative research cycles.
    -   `Writing Passes`: The number of passes the writing agent takes to refine the report.
-   **Search Results**:
    -   `Initial Docs` / `Initial Web`: Number of results to fetch during initial exploration.
    -   `Main Docs` / `Main Web`: Number of results to fetch during the main research phase.
-   **Performance & Options**:
    -   `Context Limit`: Number of recent thoughts for agent context.
    -   `Max Notes`: Number of notes to generate for reranking.
    -   `Concurrent Requests`: Number of parallel operations.

### 5. Admin

This tab is only visible to users with administrator privileges.

-   **User Management**:
    -   View all registered users, their roles, and status.
    -   Create new users.
    -   Activate or deactivate user accounts.
    -   Promote users to admin or revoke admin privileges.
    -   Edit user details or delete users.
-   **System Configuration**:
    -   **Enable New User Registration**: Toggle whether new users can register themselves. If disabled, only admins can create new accounts.
