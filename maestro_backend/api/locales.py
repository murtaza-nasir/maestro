# In a real-world application, this would be more sophisticated,
# perhaps using a library like `babel`. For this task, a simple
# dictionary-based approach is sufficient.

MESSAGES = {
    "en": {
        "registration_disabled": "User registration is disabled",
        "username_exists": "Username already registered",
        "incorrect_credentials": "Incorrect username or password",
        "login_successful": "Login successful",
        "logout_successful": "Logout successful",
        "incorrect_password": "Current password is incorrect",
        "password_changed": "Password changed successfully",
    },
    "pt": {
        "registration_disabled": "O registro de usuários está desabilitado",
        "username_exists": "Nome de usuário já registrado",
        "incorrect_credentials": "Nome de usuário ou senha incorretos",
        "login_successful": "Login bem-sucedido",
        "logout_successful": "Logout bem-sucedido",
        "incorrect_password": "A senha atual está incorreta",
        "password_changed": "Senha alterada com sucesso",
    }
}

def get_message(key: str, lang: str = "pt") -> str:
    """
    Retrieves a translated message for a given key and language.
    Defaults to English if the key is not found in the specified language.
    """
    return MESSAGES.get(lang, MESSAGES["en"]).get(key, MESSAGES["en"].get(key, key))
