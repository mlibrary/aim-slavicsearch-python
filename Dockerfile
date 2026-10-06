FROM debian:bookworm

LABEL maintainer="dfulmer@umich.edu"

RUN apt-get update && apt-get install -y --no-install-recommends \
  git \
  wget \
  curl \
  build-essential \
  perl \
  cpanminus \
  libxml2-dev \
  libxslt1-dev \
  libyaz-dev \
  yaz \
  python3 \
  python3-pip \
  python3-venv \
  python3-tk \
  && rm -rf /var/lib/apt/lists/*

RUN wget --no-check-certificate http://ftp.indexdata.dk/pub/yaz/yaz-5.30.0.tar.gz
RUN tar -xzf yaz-5.30.0.tar.gz
RUN cd yaz-5.30.0 && ./configure && make && make install

RUN cpanm MARC::Batch
RUN cpanm MARC::Lint
RUN cpanm Net::Z3950::ZOOM
RUN cpanm Dotenv

RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN python -m pip install --no-cache-dir \
  requests \
  pymarc \
  pytest \
  bookops-worldcat \
  openpyxl \
  paramiko

ARG UNAME=app
ARG UID=1000
ARG GID=1000
RUN groupadd -g ${GID} -o ${UNAME}
RUN useradd -m -d /app -u ${UID} -g ${GID} -o -s /bin/bash ${UNAME}
USER $UNAME

WORKDIR /app
ENV PERL5LIB=/app/lib