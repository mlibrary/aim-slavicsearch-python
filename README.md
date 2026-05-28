# aim-slavicsearch-python

## Setup

Clone the repo

```
git clone [address from above]
cd aim-slavicsearch-python
```

copy .env-example to .env

```
cp .env-example .env
```

edit .env with actual environment variables.

Open the folder in a container in VS Code.

## Usage Extract Search Keys - Python
Put your MARC binary file in the directory where you cloned the repository.
Give the command:  
```python3 dfulmer/processor.py -i [name of the MARC binary file] -o [<out_base>]```

An example:  
```python3 dfulmer/processor.py -i infile.mrc -o thisistheoutputpy```

## Usage Extract Search Keys - Perl
Put your MARC binary file in the directory where you cloned the repository.
Give the command:  
```perl slvr_extract.pl -i [name of the MARC binary file] -o [<out_base>]```

An example:
```perl slvr_extract.pl -i infile.mrc -o thisistheoutputpl```

This will create two files:  
<out_base>_rpt.txt  
<out_base>.txt  

## Usage Search for Matches - Perl
The next script uses the search keys of the last script to search for matches:

```perl slvr_report.pl  -i <out_base>.txt -o slvr_<date>```

An example:
```perl slvr_report.pl  -i June_search_20230606.txt -o slvr_20240808```

## Comparing the output for Extract Search Keys

To compare the reports:  
```diff thisistheoutputpl_rpt.txt thisistheoutputpy_rpt.txt```

To compare the .txt files:  
```diff thisistheoutputpl.txt thisistheoutputpy.txt```

## Running the tests
```pytest```

## Background

Slavic search processing documentation  
[https://mlit.atlassian.net/wiki/spaces/LSO/pages/9419325444/Slavic+search+processing](https://mlit.atlassian.net/wiki/spaces/LSO/pages/9419325444/Slavic+search+processing)

## Utilities
Not all MARC records come with Leader position 9 = a but if they're from Alma they should have that. ```set_leader_a.py``` will set all the Leader position 9s to a in a MARC binary file. Run it like this:

```python3 set_leader_a.py testfile.mrc```

and it will create the file testfile_with_as.mrc
