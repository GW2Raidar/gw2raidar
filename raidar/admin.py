from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse

from .models import Era, Category, Area, Account, Encounter, Participation, UserProfile


# XXX HACK https://stackoverflow.com/q/46460800/240443
from django.utils.text import smart_split, unescape_string_literal
from django.db import models
from functools import reduce
import operator
from django.contrib.admin.utils import lookup_needs_distinct
class QuotedSearchModelAdmin(admin.ModelAdmin):
    def get_search_results(self, request, queryset, search_term):
        """
        Returns a tuple containing a queryset to implement the search,
        and a boolean indicating if the results may contain duplicates.
        """
        # Apply keyword searches.
        def construct_search(field_name):
            if field_name.startswith('^'):
                return "%s__istartswith" % field_name[1:]
            elif field_name.startswith('='):
                return "%s__iexact" % field_name[1:]
            elif field_name.startswith('@'):
                return "%s__search" % field_name[1:]
            else:
                return "%s__icontains" % field_name

        # Group using quotes
        def unescape_string_literal_if_possible(bit):
            try:
                return unescape_string_literal(bit)
            except ValueError:
                return bit

        use_distinct = False
        search_fields = self.get_search_fields(request)
        if search_fields and search_term:
            search_term_list = [unescape_string_literal_if_possible(bit)
                                for bit in smart_split(search_term)]
            orm_lookups = [construct_search(str(search_field))
                           for search_field in search_fields]
            for bit in search_term_list:
                or_queries = [models.Q(**{orm_lookup: bit})
                              for orm_lookup in orm_lookups]
                queryset = queryset.filter(reduce(operator.or_, or_queries))
            if not use_distinct:
                for search_spec in orm_lookups:
                    if lookup_needs_distinct(self.opts, search_spec):
                        use_distinct = True
                        break

        return queryset, use_distinct


def admin_link(instance, title):
    urlname = 'admin:%s_%s_change' % (instance._meta.app_label, instance._meta.model_name)
    url = reverse(urlname, args=(instance.id,))
    return format_html(u'<a href="{}">{}</a>', url, title)



class EraAdmin(QuotedSearchModelAdmin):
    search_fields = ('^name',)
    list_display = ('id', 'name', 'started_at')

class CategoryAdmin(QuotedSearchModelAdmin):
    search_fields = ('^name',)
    list_display = ('id', 'name')

class AreaAdmin(QuotedSearchModelAdmin):
    search_fields = ('^name',)
    list_display = ('id', 'name')

class EncounterParticipationInline(admin.TabularInline):
    def account_admin_link(self, instance):
        return admin_link(instance.account, instance.account.name)
    account_admin_link.short_description = "Account"

    model = Participation
    list_display = ('party', 'account_admin_link', 'character', 'profession', 'archetype', 'elite')
    readonly_fields = ('party', 'account_admin_link', 'character', 'profession', 'elite')
    exclude = ('account',)
    ordering = ('party', 'character')
    extra = 0

class EncounterAdmin(QuotedSearchModelAdmin):
    def url_id_link(self, obj):
        # HACK but works
        return format_html("<a href='../../../encounter/{url_id}'>{url_id}</a>", url_id=obj.url_id)
    url_id_link.short_description = "Link"

    search_fields = ('=url_id', '=filename', '=tags__name', '=category__name')
    list_display = ('filename', 'url_id_link', 'area', 'success', 'category', 'started_at', 'duration', 'uploaded_at', 'uploaded_by')
    list_select_related = ('category', 'uploaded_by', 'area')
    inlines = (EncounterParticipationInline,)
    readonly_fields = ('url_id', 'started_at', 'duration', 'uploaded_at', 'uploaded_by', 'area', 'filename')

    # hack, but... ugly otherwise
    class Media:
        css = { 'all' : ('raidar/hide_admin_original.css',) }

class AccountParticipationInline(admin.TabularInline):
    def encounter_admin_link(self, instance):
        return admin_link(instance.encounter, instance.encounter.url_id)
    encounter_admin_link.short_description = "Encounter"

    model = Participation
    list_display = ('character', 'encounter_admin_link', 'profession', 'archetype', 'elite')
    readonly_fields = ('character', 'encounter_admin_link', 'profession', 'elite')
    exclude = ('encounter', 'party')
    extra = 0

class AccountAdmin(QuotedSearchModelAdmin):
    search_fields = ('^name', '=user__username')
    list_display = ('name', 'user')
    readonly_fields = ('name',)
    inlines = (AccountParticipationInline,)

    # hack, but... ugly otherwise
    class Media:
        css = { 'all' : ('raidar/hide_admin_original.css',) }


admin.site.register(Area, AreaAdmin)
admin.site.register(Era, EraAdmin)
admin.site.register(Category, CategoryAdmin)
admin.site.register(Account, AccountAdmin)
admin.site.register(Encounter, EncounterAdmin)
admin.site.register(UserProfile)
