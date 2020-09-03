git-eaf-corpus-stats
====================

This is a simple web app that allows viewing basic statistics on an ELAN corpus through a web interface. It is assumed that the EAF files of the corpus are stored in a bare git repository on the same server where this app is deployed. If you want to calculate total duration of sound files, they have to be stored in a separate, non-repository folder on that server.

## Git hooks
The ``hooks`` folder contains a [post-receive hook](https://git-scm.com/docs/githooks), which launches a Python script to count and log basic statistics about an ELAN corpus in JSON format. The statistics includes token count and total transcribed duration by speaker. You have to put both files to the ``hooks`` folder of your repository and make them executable. The script will run every time you push to the repository. Paths to the log directory and sound files have to be configured in ``post-receive`` file through arguments in class/function calls.

## Web interface
The web interface is written in Python+Flask. Upon request from a client, it reads the reports produced by Git hooks, processes them and sends them to the client as an HTML page. It can process multiple corpora at once. Paths to the log files and corpus names should be configured in ``conf/corpora.json``.
