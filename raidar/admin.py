from django.contrib import admin

from .models import Era, Area, Account, Character, Encounter, Participation, UserProfile

class EraAdmin(admin.ModelAdmin):
    search_fields = ('name',)
    list_display = ('id', 'name', 'started_at')

class AreaAdmin(admin.ModelAdmin):
    search_fields = ('name',)
    list_display = ('id', 'name')

class ParticipationInline(admin.TabularInline):
    model = Participation
    extra = 10
    max_num = 10
    readonly_fields = ('character', 'elite', 'party')

class EncounterAdmin(admin.ModelAdmin):
    search_fields = ('url_id', 'filename')
    list_display = ('url_id', 'filename', 'area', 'success', 'started_at', 'duration', 'uploaded_at', 'uploaded_by')
    inlines = (ParticipationInline,)
    readonly_fields = ('url_id', 'started_at', 'duration', 'uploaded_at', 'uploaded_by', 'area', 'filename')

    # hack, but... ugly otherwise
    class Media:
        css = { 'all' : ('raidar/hide_admin_original.css',) }

class CharacterAdmin(admin.ModelAdmin):
    search_fields = ('name', 'account__name', 'account__user__username')
    list_display = ('name', 'profession', 'account')
    readonly_fields = ('account', 'name', 'profession')

class CharacterInline(admin.TabularInline):
    model = Character
    readonly_fields = ('name', 'profession')
    extra = 1

class AccountAdmin(admin.ModelAdmin):
    search_fields = ('name', 'user__username')
    list_display = ('name', 'user')
    inlines = (CharacterInline,)
    readonly_fields = ('name',)

    # hack, but... ugly otherwise
    class Media:
        css = { 'all' : ('raidar/hide_admin_original.css',) }

admin.site.register(Area, AreaAdmin)
admin.site.register(Era, EraAdmin)
admin.site.register(Account, AccountAdmin)
admin.site.register(Character, CharacterAdmin)
admin.site.register(Encounter, EncounterAdmin)
admin.site.register(UserProfile)
