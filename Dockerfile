FROM python:3.8-alpine
ENV MAGICK_HOME=/usr
RUN apk add --no-cache gcc ffmpeg imagemagick imagemagick-dev musl-dev
RUN pip install wand yarl telepot multidict
COPY . .
CMD ["python", "visitelche.py"]