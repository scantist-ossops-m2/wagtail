from django.contrib.admin.utils import quote
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils.timezone import now

from wagtail.admin.admin_url_finder import AdminURLFinder
from wagtail.admin.panels import get_edit_handler
from wagtail.admin.staticfiles import versioned_static
from wagtail.blocks.field_block import FieldBlockAdapter
from wagtail.coreutils import get_dummy_request
from wagtail.models import Locale, Workflow, WorkflowContentType
from wagtail.snippets.blocks import SnippetChooserBlock
from wagtail.snippets.widgets import AdminSnippetChooser
from wagtail.test.testapp.models import (
    Advert,
    DraftStateModel,
    FullFeaturedSnippet,
    ModeratedModel,
    SnippetChooserModel,
)
from wagtail.test.utils import WagtailTestUtils


class TestCustomIcon(WagtailTestUtils, TestCase):
    def setUp(self):
        self.user = self.login()
        self.object = FullFeaturedSnippet.objects.create(
            text="test snippet with custom icon"
        )
        self.revision_1 = self.object.save_revision()
        self.revision_1.publish()
        self.object.text = "test snippet with custom icon (updated)"
        self.revision_2 = self.object.save_revision()

    def get_url(self, url_name, args=()):
        return reverse(self.object.snippet_viewset.get_url_name(url_name), args=args)

    def test_get_views(self):
        pk = quote(self.object.pk)
        views = [
            ("list", []),
            ("add", []),
            ("edit", [pk]),
            ("delete", [pk]),
            ("usage", [pk]),
            ("unpublish", [pk]),
            ("workflow_history", [pk]),
            ("revisions_revert", [pk, self.revision_1.id]),
            ("revisions_compare", [pk, self.revision_1.id, self.revision_2.id]),
            ("revisions_unschedule", [pk, self.revision_2.id]),
        ]
        for view_name, args in views:
            with self.subTest(view_name=view_name):
                response = self.client.get(self.get_url(view_name, args))
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context["header_icon"], "cog")
                self.assertContains(response, "icon icon-cog", count=1)
                # TODO: Make the list view use the shared header template
                if view_name != "list":
                    self.assertTemplateUsed(response, "wagtailadmin/shared/header.html")

    def test_get_history(self):
        response = self.client.get(self.get_url("history", [quote(self.object.pk)]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "wagtailadmin/shared/header.html")
        # History view icon is not configurable for consistency with pages
        self.assertEqual(response.context["header_icon"], "history")
        self.assertContains(response, "icon icon-history")
        self.assertNotContains(response, "icon icon-cog")

    def test_get_workflow_history_detail(self):
        # Assign default workflow to the snippet model
        self.content_type = ContentType.objects.get_for_model(type(self.object))
        self.workflow = Workflow.objects.first()
        WorkflowContentType.objects.create(
            content_type=self.content_type,
            workflow=self.workflow,
        )
        self.object.text = "Edited!"
        self.object.save_revision()
        workflow_state = self.workflow.start(self.object, self.user)
        response = self.client.get(
            self.get_url(
                "workflow_history_detail", [quote(self.object.pk), workflow_state.id]
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "wagtailadmin/shared/header.html")
        # The icon is not displayed in the header,
        # but it is displayed in the main content
        self.assertEqual(response.context["header_icon"], "list-ul")
        self.assertContains(response, "icon icon-list-ul")
        self.assertContains(response, "icon icon-cog")


class TestSnippetChooserBlockWithIcon(TestCase):
    def test_adapt(self):
        block = SnippetChooserBlock(FullFeaturedSnippet)

        block.set_name("test_snippetchooserblock")
        js_args = FieldBlockAdapter().js_args(block)

        self.assertEqual(js_args[0], "test_snippetchooserblock")
        self.assertIsInstance(js_args[1], AdminSnippetChooser)
        self.assertEqual(js_args[1].model, FullFeaturedSnippet)
        # It should use the icon defined in the FullFeaturedSnippetViewSet
        self.assertEqual(js_args[2]["icon"], "cog")

    def test_deconstruct(self):
        block = SnippetChooserBlock(FullFeaturedSnippet, required=False)
        path, args, kwargs = block.deconstruct()
        self.assertEqual(path, "wagtail.snippets.blocks.SnippetChooserBlock")
        self.assertEqual(args, (FullFeaturedSnippet,))
        # It should not add any extra kwargs for the icon
        self.assertEqual(kwargs, {"required": False})


class TestSnippetChooserPanelWithIcon(WagtailTestUtils, TestCase):
    def setUp(self):
        self.user = self.login()
        self.request = get_dummy_request()
        self.request.user = self.user
        self.text = "Test full-featured snippet with icon text"
        test_snippet = SnippetChooserModel.objects.create(
            advert=Advert.objects.create(text="foo"),
            full_featured=FullFeaturedSnippet.objects.create(text=self.text),
        )

        self.edit_handler = get_edit_handler(SnippetChooserModel)
        self.form_class = self.edit_handler.get_form_class()
        form = self.form_class(instance=test_snippet)
        edit_handler = self.edit_handler.get_bound_panel(
            instance=test_snippet, form=form, request=self.request
        )

        self.object_chooser_panel = [
            panel
            for panel in edit_handler.children
            if getattr(panel, "field_name", None) == "full_featured"
        ][0]

    def test_render_html(self):
        field_html = self.object_chooser_panel.render_html()
        self.assertIn(self.text, field_html)
        self.assertIn("Choose full-featured snippet", field_html)
        self.assertIn("Choose another full-featured snippet", field_html)
        self.assertIn("icon icon-cog icon", field_html)

        # make sure no snippet icons remain
        self.assertNotIn("icon-snippet", field_html)

    def test_render_as_empty_field(self):
        test_snippet = SnippetChooserModel()
        form = self.form_class(instance=test_snippet)
        edit_handler = self.edit_handler.get_bound_panel(
            instance=test_snippet, form=form, request=self.request
        )

        snippet_chooser_panel = [
            panel
            for panel in edit_handler.children
            if getattr(panel, "field_name", None) == "full_featured"
        ][0]

        field_html = snippet_chooser_panel.render_html()
        self.assertIn("Choose full-featured snippet", field_html)
        self.assertIn("Choose another full-featured snippet", field_html)
        self.assertIn("icon icon-cog icon", field_html)

        # make sure no snippet icons remain
        self.assertNotIn("icon-snippet", field_html)

    def test_chooser_popup(self):
        chooser_viewset = FullFeaturedSnippet.snippet_viewset.chooser_viewset
        response = self.client.get(reverse(chooser_viewset.get_url_name("choose")))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["header_icon"], "cog")
        self.assertContains(response, "icon icon-cog", count=1)
        self.assertEqual(response.context["icon"], "cog")

        # make sure no snippet icons remain
        for key in response.context.keys():
            if "icon" in key:
                self.assertNotIn("snippet", response.context[key])


class TestAdminURLs(WagtailTestUtils, TestCase):
    def setUp(self):
        self.user = self.login()

    def test_default_url_namespace(self):
        snippet = Advert.objects.create(text="foo")
        viewset = snippet.snippet_viewset
        # Accessed via the viewset
        self.assertEqual(
            viewset.get_admin_url_namespace(),
            "wagtailsnippets_tests_advert",
        )
        # Accessed via the model
        self.assertEqual(
            snippet.get_admin_url_namespace(),
            "wagtailsnippets_tests_advert",
        )
        # Get specific URL name
        self.assertEqual(
            viewset.get_url_name("edit"),
            "wagtailsnippets_tests_advert:edit",
        )
        # Chooser namespace
        self.assertEqual(
            viewset.get_chooser_admin_url_namespace(),
            "wagtailsnippetchoosers_tests_advert",
        )
        # Get specific chooser URL name
        self.assertEqual(
            viewset.chooser_viewset.get_url_name("choose"),
            "wagtailsnippetchoosers_tests_advert:choose",
        )

    def test_default_admin_base_path(self):
        snippet = Advert.objects.create(text="foo")
        viewset = snippet.snippet_viewset
        pk = quote(snippet.pk)
        expected_url = f"/admin/snippets/tests/advert/edit/{pk}/"
        expected_choose_url = "/admin/snippets/choose/tests/advert/"

        # Accessed via the viewset
        self.assertEqual(viewset.get_admin_base_path(), "snippets/tests/advert")
        # Accessed via the model
        self.assertEqual(snippet.get_admin_base_path(), "snippets/tests/advert")
        # Get specific URL
        self.assertEqual(reverse(viewset.get_url_name("edit"), args=[pk]), expected_url)
        # Ensure AdminURLFinder returns the correct URL
        url_finder = AdminURLFinder(self.user)
        self.assertEqual(url_finder.get_edit_url(snippet), expected_url)
        # Chooser base path
        self.assertEqual(
            viewset.get_chooser_admin_base_path(),
            "snippets/choose/tests/advert",
        )
        # Get specific chooser URL
        self.assertEqual(
            reverse(viewset.chooser_viewset.get_url_name("choose")),
            expected_choose_url,
        )

    def test_custom_url_namespace(self):
        snippet = FullFeaturedSnippet.objects.create(text="customised")
        viewset = snippet.snippet_viewset
        # Accessed via the viewset
        self.assertEqual(viewset.get_admin_url_namespace(), "some_namespace")
        # Accessed via the model
        self.assertEqual(snippet.get_admin_url_namespace(), "some_namespace")
        # Get specific URL name
        self.assertEqual(viewset.get_url_name("edit"), "some_namespace:edit")
        # Chooser namespace
        self.assertEqual(
            viewset.get_chooser_admin_url_namespace(),
            "my_chooser_namespace",
        )
        # Get specific chooser URL name
        self.assertEqual(
            viewset.chooser_viewset.get_url_name("choose"),
            "my_chooser_namespace:choose",
        )

    def test_custom_admin_base_path(self):
        snippet = FullFeaturedSnippet.objects.create(text="customised")
        viewset = snippet.snippet_viewset
        pk = quote(snippet.pk)
        expected_url = f"/admin/deep/within/the/admin/edit/{pk}/"
        expected_choose_url = "/admin/choose/wisely/"
        # Accessed via the viewset
        self.assertEqual(viewset.get_admin_base_path(), "deep/within/the/admin")
        # Accessed via the model
        self.assertEqual(snippet.get_admin_base_path(), "deep/within/the/admin")
        # Get specific URL
        self.assertEqual(reverse(viewset.get_url_name("edit"), args=[pk]), expected_url)
        # Ensure AdminURLFinder returns the correct URL
        url_finder = AdminURLFinder(self.user)
        self.assertEqual(url_finder.get_edit_url(snippet), expected_url)
        # Chooser base path
        self.assertEqual(
            viewset.get_chooser_admin_base_path(),
            "choose/wisely",
        )
        # Get specific chooser URL
        self.assertEqual(
            reverse(viewset.chooser_viewset.get_url_name("choose")),
            expected_choose_url,
        )


class TestPagination(WagtailTestUtils, TestCase):
    def setUp(self):
        self.user = self.login()

    @classmethod
    def setUpTestData(cls):
        default_locale = Locale.get_default()
        objects = [
            FullFeaturedSnippet(text=f"Snippet {i}", locale=default_locale)
            for i in range(32)
        ]
        FullFeaturedSnippet.objects.bulk_create(objects)
        objects = [Advert(text=f"Snippet {i}") for i in range(32)]
        Advert.objects.bulk_create(objects)

    def test_default_list_pagination(self):
        list_url = reverse(Advert.snippet_viewset.get_url_name("list"))
        response = self.client.get(list_url)

        # Default is 20 per page
        self.assertEqual(Advert.objects.all().count(), 32)
        self.assertContains(response, "Page 1 of 2")
        self.assertContains(response, "Next")
        self.assertContains(response, list_url + "?p=2")

    def test_custom_list_pagination(self):
        list_url = reverse(FullFeaturedSnippet.snippet_viewset.get_url_name("list"))
        response = self.client.get(list_url)

        # FullFeaturedSnippet is set to display 5 per page
        self.assertEqual(FullFeaturedSnippet.objects.all().count(), 32)
        self.assertContains(response, "Page 1 of 7")
        self.assertContains(response, "Next")
        self.assertContains(response, list_url + "?p=2")

    def test_default_chooser_pagination(self):
        chooser_viewset = Advert.snippet_viewset.chooser_viewset
        choose_url = reverse(chooser_viewset.get_url_name("choose"))
        choose_results_url = reverse(chooser_viewset.get_url_name("choose_results"))
        response = self.client.get(choose_url)

        # Default is 10 per page
        self.assertEqual(Advert.objects.all().count(), 32)
        self.assertContains(response, "Page 1 of 4")
        self.assertContains(response, "Next")
        self.assertContains(response, choose_results_url + "?p=2")

    def test_custom_chooser_pagination(self):
        chooser_viewset = FullFeaturedSnippet.snippet_viewset.chooser_viewset
        choose_url = reverse(chooser_viewset.get_url_name("choose"))
        choose_results_url = reverse(chooser_viewset.get_url_name("choose_results"))
        response = self.client.get(choose_url)

        # FullFeaturedSnippet is set to display 15 per page
        self.assertEqual(FullFeaturedSnippet.objects.all().count(), 32)
        self.assertContains(response, "Page 1 of 3")
        self.assertContains(response, "Next")
        self.assertContains(response, choose_results_url + "?p=2")


class TestFilterSetClass(WagtailTestUtils, TestCase):
    def setUp(self):
        self.login()

    def get_url(self, url_name, args=()):
        return reverse(
            FullFeaturedSnippet.snippet_viewset.get_url_name(url_name), args=args
        )

    def get(self, params={}):
        return self.client.get(self.get_url("list"), params)

    def create_test_snippets(self):
        FullFeaturedSnippet.objects.create(
            text="Nasi goreng from Indonesia", country_code="ID"
        )
        FullFeaturedSnippet.objects.create(
            text="Fish and chips from the UK", country_code="UK"
        )

    def test_get_include_filters_form_media(self):
        response = self.get()
        html = response.content.decode()
        datetime_js = versioned_static("wagtailadmin/js/date-time-chooser.js")

        # The script file for the date time chooser should be included
        self.assertTagInHTML(f'<script src="{datetime_js}"></script>', html)

    def test_unfiltered_no_results(self):
        response = self.get()
        add_url = self.get_url("add")
        self.assertContains(
            response,
            f'No full-featured snippets have been created. Why not <a href="{add_url}">add one</a>',
        )
        self.assertContains(
            response,
            '<label for="id_country_code_0"><input type="radio" name="country_code" value="" id="id_country_code_0" checked>All</label>',
            html=True,
        )
        self.assertTemplateUsed(response, "wagtailadmin/shared/filters.html")

    def test_unfiltered_with_results(self):
        self.create_test_snippets()
        response = self.get()
        self.assertTemplateUsed(response, "wagtailadmin/shared/filters.html")
        self.assertContains(response, "Nasi goreng from Indonesia")
        self.assertContains(response, "Fish and chips from the UK")
        self.assertNotContains(response, "There are 2 matches")
        self.assertContains(
            response,
            '<label for="id_country_code_0"><input type="radio" name="country_code" value="" id="id_country_code_0" checked>All</label>',
            html=True,
        )

    def test_empty_filter_with_results(self):
        self.create_test_snippets()
        response = self.get({"country_code": ""})
        self.assertTemplateUsed(response, "wagtailadmin/shared/filters.html")
        self.assertContains(response, "Nasi goreng from Indonesia")
        self.assertContains(response, "Fish and chips from the UK")
        self.assertNotContains(response, "There are 2 matches")
        self.assertContains(
            response,
            '<label for="id_country_code_0"><input type="radio" name="country_code" value="" id="id_country_code_0" checked>All</label>',
            html=True,
        )

    def test_filtered_no_results(self):
        self.create_test_snippets()
        response = self.get({"country_code": "PH"})
        self.assertTemplateUsed(response, "wagtailadmin/shared/filters.html")
        self.assertContains(
            response, "Sorry, no full-featured snippets match your query"
        )
        self.assertContains(
            response,
            '<label for="id_country_code_2"><input type="radio" name="country_code" value="PH" id="id_country_code_2" checked>Philippines</label>',
            html=True,
        )

    def test_filtered_with_results(self):
        self.create_test_snippets()
        response = self.get({"country_code": "ID"})
        self.assertTemplateUsed(response, "wagtailadmin/shared/filters.html")
        self.assertContains(response, "Nasi goreng from Indonesia")
        self.assertContains(response, "There is 1 match")
        self.assertContains(
            response,
            '<label for="id_country_code_1"><input type="radio" name="country_code" value="ID" id="id_country_code_1" checked>Indonesia</label>',
            html=True,
        )


class TestFilterSetClassSearch(WagtailTestUtils, TransactionTestCase):
    fixtures = ["test_empty.json"]

    def setUp(self):
        self.login()

    def get_url(self, url_name, args=()):
        return reverse(
            FullFeaturedSnippet.snippet_viewset.get_url_name(url_name), args=args
        )

    def get(self, params={}):
        return self.client.get(self.get_url("list"), params)

    def create_test_snippets(self):
        FullFeaturedSnippet.objects.create(
            text="Nasi goreng from Indonesia", country_code="ID"
        )
        FullFeaturedSnippet.objects.create(
            text="Fish and chips from the UK", country_code="UK"
        )

    def test_filtered_searched_no_results(self):
        self.create_test_snippets()
        response = self.get({"country_code": "ID", "q": "chips"})
        self.assertTemplateUsed(response, "wagtailadmin/shared/filters.html")
        self.assertContains(
            response, "Sorry, no full-featured snippets match your query"
        )
        self.assertContains(
            response,
            '<label for="id_country_code_1"><input type="radio" name="country_code" value="ID" id="id_country_code_1" checked>Indonesia</label>',
            html=True,
        )

    def test_filtered_searched_with_results(self):
        self.create_test_snippets()
        response = self.get({"country_code": "UK", "q": "chips"})
        self.assertTemplateUsed(response, "wagtailadmin/shared/filters.html")
        self.assertContains(response, "Fish and chips from the UK")
        self.assertContains(response, "There is 1 match")
        self.assertContains(
            response,
            '<label for="id_country_code_3"><input type="radio" name="country_code" value="UK" id="id_country_code_3" checked>United Kingdom</label>',
            html=True,
        )


class TestListFilterWithList(WagtailTestUtils, TestCase):
    model = DraftStateModel

    def setUp(self):
        self.login()
        self.date = now()
        self.date_str = self.date.isoformat()

    def get_url(self, url_name, args=()):
        return reverse(self.model.snippet_viewset.get_url_name(url_name), args=args)

    def get(self, params={}):
        return self.client.get(self.get_url("list"), params)

    def create_test_snippets(self):
        self.model.objects.create(text="The first created object")
        self.model.objects.create(
            text="A second one after that",
            first_published_at=self.date,
        )

    def test_get_include_filters_form_media(self):
        response = self.get()
        html = response.content.decode()
        datetime_js = versioned_static("wagtailadmin/js/date-time-chooser.js")

        # The script file for the date time chooser should be included
        self.assertTagInHTML(f'<script src="{datetime_js}"></script>', html)

    def test_unfiltered_no_results(self):
        response = self.get()
        add_url = self.get_url("add")
        self.assertContains(
            response,
            f'No {self.model._meta.verbose_name_plural} have been created. Why not <a href="{add_url}">add one</a>',
        )
        self.assertContains(
            response,
            '<label class="w-field__label" for="id_first_published_at" id="id_first_published_at-label">First published at</label>',
            html=True,
        )
        self.assertContains(
            response,
            '<input type="text" name="first_published_at" autocomplete="off" id="id_first_published_at">',
            html=True,
        )
        self.assertTemplateUsed(response, "wagtailadmin/shared/filters.html")

    def test_unfiltered_with_results(self):
        self.create_test_snippets()
        response = self.get()
        self.assertTemplateUsed(response, "wagtailadmin/shared/filters.html")
        self.assertContains(response, "The first created object")
        self.assertContains(response, "A second one after that")
        self.assertNotContains(response, "There are 2 matches")
        self.assertContains(
            response,
            '<label class="w-field__label" for="id_first_published_at" id="id_first_published_at-label">First published at</label>',
            html=True,
        )
        self.assertContains(
            response,
            '<input type="text" name="first_published_at" autocomplete="off" id="id_first_published_at">',
            html=True,
        )

    def test_empty_filter_with_results(self):
        self.create_test_snippets()
        response = self.get({"first_published_at": ""})
        self.assertTemplateUsed(response, "wagtailadmin/shared/filters.html")
        self.assertContains(response, "The first created object")
        self.assertContains(response, "A second one after that")
        self.assertNotContains(response, "There are 2 matches")
        self.assertContains(
            response,
            '<label class="w-field__label" for="id_first_published_at" id="id_first_published_at-label">First published at</label>',
            html=True,
        )
        self.assertContains(
            response,
            '<input type="text" name="first_published_at" value="" autocomplete="off" id="id_first_published_at">',
            html=True,
        )

    def test_filtered_no_results(self):
        self.create_test_snippets()
        response = self.get({"first_published_at": "1970-01-01"})
        self.assertTemplateUsed(response, "wagtailadmin/shared/filters.html")
        self.assertContains(
            response,
            f"Sorry, no {self.model._meta.verbose_name_plural} match your query",
        )
        self.assertContains(
            response,
            '<label class="w-field__label" for="id_first_published_at" id="id_first_published_at-label">First published at</label>',
            html=True,
        )
        self.assertContains(
            response,
            '<input type="text" name="first_published_at" value="1970-01-01" autocomplete="off" id="id_first_published_at">',
            html=True,
        )

    def test_filtered_with_results(self):
        self.create_test_snippets()
        response = self.get({"first_published_at": self.date_str})
        self.assertTemplateUsed(response, "wagtailadmin/shared/filters.html")
        self.assertContains(response, "A second one after that")
        self.assertContains(response, "There is 1 match")
        self.assertContains(
            response,
            '<label class="w-field__label" for="id_first_published_at" id="id_first_published_at-label">First published at</label>',
            html=True,
        )
        self.assertContains(
            response,
            f'<input type="text" name="first_published_at" value="{self.date_str}" autocomplete="off" id="id_first_published_at">',
            html=True,
        )


class TestListFilterWithDict(TestListFilterWithList):
    model = ModeratedModel

    def test_filtered_contains_with_results(self):
        self.create_test_snippets()
        response = self.get({"text__contains": "second one"})
        self.assertTemplateUsed(response, "wagtailadmin/shared/filters.html")
        self.assertContains(response, "A second one after that")
        self.assertContains(response, "There is 1 match")
        self.assertContains(
            response,
            '<label class="w-field__label" for="id_text__contains" id="id_text__contains-label">Text contains</label>',
            html=True,
        )
        self.assertContains(
            response,
            '<input type="text" name="text__contains" value="second one" id="id_text__contains">',
            html=True,
        )


class TestListViewWithCustomColumns(WagtailTestUtils, TestCase):
    def setUp(self):
        self.login()

    @classmethod
    def setUpTestData(cls):
        FullFeaturedSnippet.objects.create(text="From Indonesia", country_code="ID")
        FullFeaturedSnippet.objects.create(text="From the UK", country_code="UK")

    def get_url(self, url_name, args=()):
        return reverse(
            FullFeaturedSnippet.snippet_viewset.get_url_name(url_name), args=args
        )

    def get(self, params={}):
        return self.client.get(self.get_url("list"), params)

    def test_custom_columns(self):
        response = self.get()
        self.assertContains(response, "Text")
        self.assertContains(response, "Country Code")
        self.assertContains(response, "Custom Foo Column")
        self.assertContains(response, "Updated")

        self.assertContains(response, "Foo UK")

        list_url = self.get_url("list")
        sort_country_code_url = list_url + "?ordering=country_code"

        # One from the country code column, another from the custom foo column
        self.assertContains(response, sort_country_code_url, count=2)

        html = response.content.decode()

        # The bulk actions column plus 4 columns defined in FullFeaturedSnippetViewSet
        self.assertTagInHTML("<th>", html, count=5, allow_extra_attrs=True)


class TestCustomTemplates(WagtailTestUtils, TestCase):
    model = FullFeaturedSnippet

    def setUp(self):
        self.user = self.login()

    @classmethod
    def setUpTestData(cls):
        cls.object = cls.model.objects.create(text="Some snippet")

    def get_url(self, view_name, args=()):
        return reverse(self.model.snippet_viewset.get_url_name(view_name), args=args)

    def test_template_lookups(self):
        pk = quote(self.object.pk)
        cases = {
            "with app label and model name": (
                "add",
                [],
                "wagtailsnippets/snippets/tests/fullfeaturedsnippet/create.html",
            ),
            "with app label": (
                "edit",
                [pk],
                "wagtailsnippets/snippets/tests/edit.html",
            ),
            "without app label and model name": (
                "delete",
                [pk],
                "wagtailsnippets/snippets/delete.html",
            ),
            "override a view that uses a generic template": (
                "unpublish",
                [pk],
                "wagtailsnippets/snippets/tests/fullfeaturedsnippet/unpublish.html",
            ),
            "override with index_template_name": (
                "list",
                [],
                "tests/fullfeaturedsnippet_index.html",
            ),
            "override with get_history_template": (
                "history",
                [pk],
                "tests/snippet_history.html",
            ),
        }
        for case, (view_name, args, template_name) in cases.items():
            with self.subTest(case=case):
                response = self.client.get(self.get_url(view_name, args=args))
                self.assertTemplateUsed(response, template_name)
                self.assertContains(response, "<p>An added paragraph</p>", html=True)