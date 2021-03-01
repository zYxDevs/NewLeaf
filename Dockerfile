FROM python:3.9-buster

WORKDIR /workdir

COPY ./requirements.txt /workdir/requirements.txt

RUN pip install -r requirements.txt

COPY . /workdir

EXPOSE 3000

CMD python index.py