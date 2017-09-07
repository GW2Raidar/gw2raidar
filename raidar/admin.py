from django.contrib import admin
from django.utils.html import format_html

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
    def url_id_link(self, obj):
        # HACK but works
        return format_html("<a href='../../../encounter/{url_id}'>{url_id}</a>", url_id=obj.url_id)
    url_id_link.short_description = "Link"

    search_fields = ('url_id', 'filename', 'area__name', 'characters__name', 'characters__account__name', 'characters__account__user__username')
    list_display = ('filename', 'url_id_link', 'area', 'success', 'started_at', 'duration', 'uploaded_at', 'uploaded_by')
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
