"""Sign in with the user name or the email address (people often type their work email)."""
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class UsernameOrEmailBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        if username and "@" in username:
            User = get_user_model()
            matches = list(User.objects.filter(email__iexact=username.strip())[:2])
            if len(matches) != 1:  # unknown or shared address: behave like a wrong user name
                User().set_password(password)  # same work as a real check, so timing does not reveal accounts
                return None
            username = matches[0].get_username()
        return super().authenticate(request, username=username, password=password, **kwargs)
