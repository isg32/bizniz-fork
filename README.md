# Munni AI - FastAPI Business Platform

Welcome to Munni AI, a robust SaaS boilerplate built with a modern Python stack. This project provides a complete foundation for building a business around a coin-based API, including a professional website, user authentication, a payment system, and a secure API for external applications.

### ✨ Features

*   **Professional Website**: Built with FastAPI and Jinja2, styled with DaisyUI.
*   **User Management**: Full registration, login, logout, and session management powered by PocketBase.
*   **Payment Integration**: Complete checkout flow and order fulfillment using Stripe Checkout and Webhooks.
*   **Coin-Based Economy**: Users purchase "Coins" and spend them to use API services.
*   **Secure API**: Token-based (JWT) authentication for your desktop/mobile apps.
*   **Interactive API Docs**: Automatic documentation powered by FastAPI (Swagger UI & ReDoc).
*   **Scalable Architecture**: Clean separation of concerns between web, API, and business logic (services).

### 🛠️ Tech Stack

*   **Backend Framework**: FastAPI
*   **Database & Auth**: PocketBase
*   **Payments**: Stripe
*   **Frontend Styling**: DaisyUI (on TailwindCSS)
*   **Configuration**: Pydantic
*   **Server**: Uvicorn

---

### 🚀 Getting Started

Follow these steps to set up and run the project locally.

#### 1. Prerequisites

*   Python 3.10+
*   [PocketBase](https://pocketbase.io/docs/) executable
*   [Stripe CLI](https://stripe.com/docs/stripe-cli) (for local webhook testing)
*   A Stripe account and API keys.
*   A Google Gemini API key.

#### 2. Initial Setup

1.  **Clone the repository:**
    ```bash
    git clone <your-repo-url>
    cd <your-repo-name>
    ```

2.  **Create a virtual environment and install dependencies:**
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
    pip install -r requirements.txt
    ```

#### 3. PocketBase Configuration

1.  **Start PocketBase:**
    ```bash
    ./pocketbase serve
    ```
    Navigate to `http://127.0.0.1:8090/_/` and create your first admin account.

2.  **Create the `users` Collection:**
    *   In the PocketBase UI, create a new collection named `users`.
    *   Mark it as an **Auth** collection.
    *   Add the following fields:
        *   `name` (Type: `text`, default: empty)
        *   `coins` (Type: `number`, default: `10`)
        *   `subscription_status` (Type: `text`, default: `inactive`)
        *   `stripe_customer_id` (Type: `text`, optional - leave "Required" unchecked)
        *   `stripe_subscription_id` (Type: `text`, optional - leave "Required" unchecked)
        *   `active_plan_name` (Type: `text`, optional - leave "Required" unchecked)

#### 4. Stripe Configuration

1.  **Create Products:** In your Stripe Dashboard, go to the Products catalog and create one-time purchase products.
2.  **Add Metadata:** For each product, add a metadata field with the key `coins` and the value being the number of coins the product provides (e.g., `100`).

#### 5. Environment Configuration

1.  **Create the `.env` file:** Copy the contents from the initial setup steps into a new file named `.env` in the project root.

2.  **Fill in your credentials:** Update the `.env` file with your `SECRET_KEY`, PocketBase admin credentials, Stripe keys, and Gemini API key.

#### 6. Running the Application

1.  **Start the FastAPI Server:**
    ```bash
    uvicorn app.main:app --reload
    ```
    The application will be running at `http://127.0.0.1:8000`.

2.  **Forward Stripe Webhooks (in a separate terminal):**
    ```bash
    stripe listen --forward-to http://127.0.0.1:8000/api/v1/payments/stripe-webhook
    ```
    Copy the webhook signing secret (`whsec_...`) printed by the CLI into your `.env` file.

You now have a fully functional local development environment!

---

### Project Complete

You have successfully built a complete, professional, and scalable SaaS application.

**You have achieved:**
*   A beautiful, responsive **website** with user registration, login, a dashboard, and a pricing page.
*   A secure **authentication system** leveraging the power of PocketBase.
*   A full end-to-end **payment and fulfillment system** using Stripe.
*   A documented, secure **API** for your apps to consume.
*   A **coin-based service model** that is ready for you to add your unique AI features.

This is a massive accomplishment and a powerful foundation for your business. Congratulations
