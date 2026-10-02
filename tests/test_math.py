import unittest

from app import rendered_markdown
from paper_math import math_spans, validate_math
from paper_validation import validate_group
from paper_config import validate_pipeline


class MathTests(unittest.TestCase):
    def test_math_delimiters_skip_code_and_report_unclosed_equations(self):
        text = (r"Literal \$5 and `$ignored$`." + "\n"
                "```tex\n$also_ignored$\n```\n"
                r"$x_1$ and $$F_{A,\Theta}=f\circ g$$ and \(z\) and \[\frac{a}{b}\]")
        spans, errors = math_spans(text)
        self.assertEqual(errors, [])
        self.assertEqual(len(spans), 4)
        self.assertEqual(sum(span.display for span in spans), 2)
        self.assertIn("Unclosed math delimiter $$", math_spans("$$\\frac{a}{b}")[1][0])

    def test_katex_checks_generated_math_before_publication(self):
        formula = r"$$F_{A,\Theta} = f^{(n+1)}\circ\sigma^{(n)}\circ\cdots$$"
        self.assertEqual(validate_math(formula), [])
        self.assertTrue(any("Invalid TeX" in error for error in validate_math(r"$\notacommand{x}$")))
        config = validate_pipeline({"method_min_chars": 100})
        group = "## 제시한 방법론\n" + "방법론 설명 " * 20 + r"$\notacommand{x}$"
        self.assertTrue(any("Invalid TeX" in error for error in validate_group("B", group, "", config)))

    def test_markdown_preserves_delimiters_and_escapes_untrusted_math(self):
        html = str(rendered_markdown(r"Value $x_{a_b}$ and \(\frac{1}{2}\)."))
        self.assertIn("$x_{a_b}$", html)
        self.assertIn(r"\(\frac{1}{2}\)", html)
        self.assertNotIn("<em>", html)
        dangerous = str(rendered_markdown(r"$\text{<script>alert(1)</script>}$"))
        self.assertNotIn("<script>", dangerous)
        self.assertIn("&lt;script&gt;", dangerous)


if __name__ == "__main__":
    unittest.main()
