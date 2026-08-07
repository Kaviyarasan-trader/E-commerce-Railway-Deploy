from django import template

register = template.Library()


@register.filter
def display_name(user):
    if not user:
        return ''
    full = user.get_full_name().strip()
    if full:
        return full
    raw = (user.username or user.email or '').split('@')[0]
    if raw:
        return ' '.join(w.capitalize() for w in raw.replace('_', ' ').replace('.', ' ').split())
    return 'User'
