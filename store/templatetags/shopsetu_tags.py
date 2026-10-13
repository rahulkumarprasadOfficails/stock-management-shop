from decimal import Decimal

from django import template

register = template.Library()


@register.filter
def div(value, divisor):
    return Decimal(value) / Decimal(divisor)


@register.filter
def sub(value, other):
    return Decimal(value) - Decimal(other)


def _under_thousand(number):
    ones = ["", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"]
    teens = ["ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"]
    tens = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]
    words = []
    if number >= 100:
        words.extend([ones[number // 100], "hundred"])
        number %= 100
    if number >= 20:
        words.append(tens[number // 10])
        number %= 10
    elif number >= 10:
        words.append(teens[number - 10])
        number = 0
    if number:
        words.append(ones[number])
    return " ".join(words)


def _indian_integer(number):
    if number == 0:
        return "zero"
    chunks = []
    for divisor, label in ((1000000000, "thousand crore"), (10000000, "crore"), (100000, "lakh"), (1000, "thousand"), (100, "hundred")):
        quantity, number = divmod(number, divisor)
        if quantity:
            chunks.append(f"{_under_thousand(quantity)} {label}")
    if number:
        chunks.append(_under_thousand(number))
    return " ".join(chunks)


@register.filter
def amount_words(value):
    amount = Decimal(value)
    rupees = int(amount)
    paise = int((amount - rupees) * 100)
    phrase = f"{_indian_integer(rupees)} rupees"
    if paise:
        phrase += f" and {_indian_integer(paise)} paise"
    return phrase.title() + " only"
