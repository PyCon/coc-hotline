FROM python:3.13-bookworm AS base
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
RUN mkdir /code

WORKDIR /code

RUN pip --no-cache-dir --disable-pip-version-check install --upgrade pip setuptools wheel

COPY requirements.txt /tmp/
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r /tmp/requirements.txt

FROM base

COPY coc-hotline.py /code/coc-hotline.py
