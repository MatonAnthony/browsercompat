#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Tests for `web-platform-compat` models module."""
import mock
import unittest

from webplatformcompat.models import (
    Browser, Feature, Maturity, Section, Specification, Support, Version,
    post_save_update_cache)


class TestBrowser(unittest.TestCase):

    def test_str(self):
        browser = Browser(slug="browser")
        self.assertEqual('browser', str(browser))


class TestFeature(unittest.TestCase):

    def test_str(self):
        feature = Feature(slug="feature")
        self.assertEqual('feature', str(feature))


class TestMaturity(unittest.TestCase):
    def test_str(self):
        maturity = Maturity(key="Draft")
        self.assertEqual('Draft', str(maturity))


class TestSection(unittest.TestCase):
    def test_str(self):
        section = Section(name={'en': 'The Section'})
        self.assertEqual('The Section', str(section))

    def test_str_no_name(self):
        section = Section()
        self.assertEqual('<unnamed>', str(section))

    def test_str_no_english(self):
        section = Section(name={'es': 'En Section'})
        self.assertEqual('<unnamed>', str(section))


class TestSpecification(unittest.TestCase):
    def test_str(self):
        specification = Specification(key='Spec')
        self.assertEqual('Spec', str(specification))


class TestSupport(unittest.TestCase):

    def test_str(self):
        browser = Browser(slug='firefox')
        version = Version(browser=browser, version=1.0)
        feature = Feature(slug="feature")
        support = Support(version=version, feature=feature)
        self.assertEqual(
            'firefox 1.0 support for feature feature is yes', str(support))


class TestVersion(unittest.TestCase):

    def test_str(self):
        browser = Browser(slug="browser")
        bv = Version(browser=browser, version='1.0')
        self.assertEqual('browser 1.0', str(bv))


class TestSaveSignal(unittest.TestCase):
    def setUp(self):
        self.patcher = mock.patch(
            'webplatformcompat.tasks.update_cache_for_instance')
        self.mocked_update_cache = self.patcher.start()
        self.browser = Browser(id=666)

    def tearDown(self):
        self.patcher.stop()

    def test_raw(self):
        post_save_update_cache(Browser, self.browser, created=True, raw=True)
        self.mocked_update_cache.assertNotCalled()

    def test_create(self):
        post_save_update_cache(Browser, self.browser, created=True, raw=False)
        self.mocked_update_cache.assertCalledOnce('Browser', 666, self.browser)
