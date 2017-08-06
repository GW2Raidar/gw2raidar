from django.contrib import admin

from .models import Era, Area, Account, Character, Encounter, Participation, UserProfile

class ParticipationInline(admin.TabularInline):
    model = Participation
    extra = 10
    max_num = 10
    readonly_fields = ('character', 'elite', 'party')

class EncounterAdmin(admin.ModelAdmin):
    inlines = (ParticipationInline,)
    readonly_fields = ('url_id', 'started_at', 'duration', 'uploaded_at', 'uploaded_by', 'area', 'filename')

    # hack, but... ugly otherwise
    class Media:
        css = { 'all' : ('raidar/hide_admin_original.css',) }

class CharacterAdmin(admin.ModelAdmin):
    readonly_fields = ('account', 'name', 'profession')

class CharacterInline(admin.TabularInline):
    model = Character
    readonly_fields = ('name', 'profession')
    extra = 1

class AccountAdmin(admin.ModelAdmin):
    inlines = (CharacterInline,)
    readonly_fields = ('name',)

    # hack, but... ugly otherwise
    class Media:
        css = { 'all' : ('raidar/hide_admin_original.css',) }

admin.site.register(Area)
admin.site.register(Era)
admin.site.register(Account, AccountAdmin)
admin.site.register(Character, CharacterAdmin)
admin.site.register(Encounter, EncounterAdmin)
admin.site.register(UserProfile)
