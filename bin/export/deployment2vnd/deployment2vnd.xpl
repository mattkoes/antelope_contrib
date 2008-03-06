
use Datascope;

require "getopts.pl";

#
# here comes the main program
#

  if ( !&Getopts('tvh') || @ARGV != 2 ) {
    die ("USAGE: $0 [-v] [-t] [-h] database file \n");
  }

  $database = $ARGV[0];
  $file	= $ARGV[1];

  elog_init ($0, @ARGV) ;

  if (-e $file) {
    elog_die("File already exists!  Won't overwrite\n") ;
    exit(1);
  }


  @db		= dbopen ( $database, "r") ; 
  @deploy	= dblookup(@db, "", "deployment" , "" , "");
  elog_notify(0, "Opened database: $database \n") if ($opt_v) ;

  if (! dbquery ( @deploy, "dbTABLE_PRESENT" )) {
     elog_die("No deployment table for '$database' \n");
     exit(1);
  }   

  $nrecs = dbquery(@deploy, "dbRECORD_COUNT") ;


#
# -t option writes out data in tab separated format 
#

  if ($opt_t) { 
      elog_notify(0, "Writing out tab separted format to: $file.\n") if ($opt_t && $opt_v);
  } else {
      elog_notify(0, "Going to write out csv file: $file.\n") if ($opt_v) ;
  }

  open (FILE, "> $file")  || die "Can't open $file for writing: $! \n";

  for ($row = 0; $row < $nrecs; $row++ ) {
	$deploy[3] = $row ;
	($net, $snet, $sta, $start, $end, $equipin, $equipout, $cert, $decert, $pdcc, $sdcc) = dbgetv(@deploy, qw (net snet sta time endtime equip_install equip_remove cert_time decert_time pdcc sdcc) ) ;

#	$start_date = epoch2str ($start, "%Y/%m/%d");	
#	$start_time = epoch2str ($start, "%T");	
	$end_date = epoch2str ($end, "%Y/%m/%d");	
	$end_time = epoch2str ($end, "%T");	

	if ($equipin == -9999999999.99900 ) { 
#	    $install_date = "   ";
	    $install_date = "";
	} else { 
	    $install_date = epoch2str ($equipin, "%Y/%m/%d");	
	}

	if ($cert == -9999999999.99900 ) { 
#	    $cert_date = "   ";
	    $cert_date = "";
	} else { 
	    $cert_date = epoch2str ($cert, "%Y/%m/%d");	
	}
	
	if ($start == -9999999999.99900 ) { 
#	    $start = "   ";
	    $start_date = "";
	    $start_time = "";
	} else { 
#	    $start_date = epoch2str ($start_date, "%Y/%m/%d");	
	    $start_date = epoch2str ($start, "%Y/%m/%d");	
	    $start_time = epoch2str ($start, "%T");	
	}
#
	if ($pdcc =~/^-/) {
#	    $pdcc = "   ";
	    $pdcc = "";
	}

	if ($sdcc =~/^-/) {
#	    $sdcc = "   ";
	    $sdcc = "";
	}

	elog_notify(0, "$net\t$snet\t$sta\t$install_date\t$cert_date\t$start_date\t$start_time\t$end_date\t$end_time\t$pdcc\t$sdcc\n") if ($opt_t && $opt_v);
	print FILE  "$net\t$snet\t$sta\t$install_date\t$cert_date\t$start_date\t$start_time\t$end_date\t$end_time\t$pdcc\t$sdcc\n" if $opt_t;
	print FILE  "net\t snet\t sta\t install_date\t cert_date\t start_date\t start_time\t end_date\t end_time\t pdcc\t sdcc\n" if ($opt_h && ($row == 0 || $row == $nrecs-1) && $opt_t);
	elog_notify(0, "$net,$snet,$sta,$install_date,$cert_date,$start_date,$start_time,$end_date,$end_time,$pdcc,$sdcc\n") if (!$opt_t  && $opt_v);
	print FILE  "$net,$snet,$sta,$install_date,$cert_date,$start_date,$start_time,$end_date,$end_time,$pdcc,$sdcc\n" if !$opt_t;
	print FILE  "net,snet,sta,install_date,cert_date,start_date,start_time,end_date,end_time,pdcc,sdcc\n" if ($opt_h && ($row == 0 || $row == $nrecs-1) && !$opt_t );
   }

   close FILE;
   dbclose (@db);


sub trim {

        # from Perl Cookbook (O'Reilly) recipe 1.14, p.30

        my @out = @_ ;
        for (@out) {
             s/^\s+//;
             s/\s+$//;
        }
        return wantarray ? @out  : $out[0];
}
