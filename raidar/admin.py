from django.contrib import admin

from .models import Area, Account, Character, Encounter, Participation

class ParticipationInline(admin.TabularInline):
    model = Participation
    extra = 10
    max_num = 10

class EncounterAdmin(admin.ModelAdmin):
    inlines = (ParticipationInline,)

    # hack, but... ugly otherwise
    class Media:
        css = { 'all' : ('raidar/hide_admin_original.css',) }

class CharacterInline(admin.TabularInline):
    model = Character
    extra = 1

class AccountAdmin(admin.ModelAdmin):
    inlines = (CharacterInline,)

    # hack, but... ugly otherwise
    class Media:
        css = { 'all' : ('raidar/hide_admin_original.css',) }

admin.site.register(Area)
admin.site.register(Account, AccountAdmin)
admin.site.register(Character)
admin.site.register(Encounter, EncounterAdmin)
