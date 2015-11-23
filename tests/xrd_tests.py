#!/usr/bin/env python
"""
Test code for the calculate.xrd module
"""

# Python 2-to-3 compatibility code
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import os
import sys
sys.path.insert(0, os.path.abspath(
                   os.path.join(os.path.dirname(__file__), "../")))  # noqa
from soprano.calculate import xrd
import unittest
import numpy as np

_TESTDATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "test_data")


class TestXRDCalculator(unittest.TestCase):

    def test_func_interface(self):
        xr = xrd.XRDCalculator()
        # Test that functions and function arguments are properly
        # accepted/rejected
        # Case 1:
        # Wrong kind of function

        def bad_func(x):
            return x
        self.assertRaisesRegexp(ValueError,
                                "Invalid peak_func passed to set_peak_func",
                                xr.set_peak_func,
                                bad_func)
        # Case 2:
        # Right function, wrong arguments

        def good_func(x, w, a, b, c=0.2):
            return x*w*a*b*c
        bad_args = [0]
        self.assertRaisesRegexp(ValueError,
                                """Invalid number of peak_f_args passed to
                                    set_peak_func""",
                                xr.set_peak_func,
                                good_func,
                                bad_args)
        # Case 3:
        # All good
        good_args = [0, 0]
        try:
            xr.set_peak_func(peak_func=good_func, peak_f_args=good_args)
        except:
            self.fail("Good function not accepted")

    def test_powder_peaks(self):
        xr = xrd.XRDCalculator()

        abc = [[3,5,10],[np.pi/2, np.pi/2, np.pi/2]]
        peaks_nosym = xr.powder_peaks(latt_abc=abc)
        peaks_sym = xr.powder_peaks(latt_abc=abc, n=230, o=1)

        # A very crude test for now
        self.assertTrue(len(peaks_nosym.theta2) >= len(peaks_sym.theta2))



class TestXRDRules(unittest.TestCase):

    def test_sel_rules(self):

        # Load the data from Colan's reference file
        ref_file_ends = ['mono']

        for e in ref_file_ends:
            fname = os.path.join(_TESTDATA_DIR,
                                 "xrd_sel_test_{0}.txt".format(e))
            refdata = np.loadtxt(fname)

            n_o_pair = (0, 0)
            sel_rule = None

            for case in refdata:
                n, o, h, k, l, val = case
                n = int(n)
                o = int(o)
                if (n, o) != n_o_pair:
                    sel_rule = xrd.get_sel_rule_from_international(n, o)
                    n_o_pair = (n, o)
                self.assertEqual(sel_rule((h, k, l)), val)

if __name__ == '__main__':
    unittest.main()
