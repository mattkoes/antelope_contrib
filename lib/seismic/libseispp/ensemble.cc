#include "ensemble.h"
#include "tr.h"
namespace SEISPP {
using namespace std;
using namespace SEISPP;
//
// Ensemble constructors.  Both just create blank trace or 3c trace objects
// and push them into a vector container.
//
TimeSeriesEnsemble::TimeSeriesEnsemble()
{
	member.reserve(0);
}
TimeSeriesEnsemble::TimeSeriesEnsemble(int nensemble, int nsamples)
{
	for(int i=0; i<nensemble; ++i)
	{
		TimeSeries *ts = new TimeSeries(nsamples);
		member.push_back(*ts);
		delete ts;
	}
}
TimeSeriesEnsemble::TimeSeriesEnsemble(const TimeSeriesEnsemble& tceold)
	: Metadata(tceold)
{
	int nmembers=tceold.member.size();
	if(!member.empty()) member.clear();
	member.reserve(nmembers);
	for(int i=0; i<nmembers; ++i)
		member.push_back(tceold.member[i]);
}
//
// Currently don't define this globally in an include file
// so will place prototype inline here.  These routines come
// from Danny Harvey and do a lot of the hard part of what is
// needed here.
//
extern "C" {
int grdb_sc_loadcss(Dbptr dbin,
	char *net_expr,
		char *sta_expr,
			char *chan_expr,
				double tstart,
					double tend,
	int coords,
		int ir,
			int orient,
				Dbptr *dbscgr,
					Dbptr *dbsc);
int grtr_sc_create(Dbptr dbscgr,
	char *net_expr,
		char *sta_expr,
			char *chan_expr,
				double tstart,
					double tend,
		char *gap,
			int calib,
				int ir,
					Dbptr *dbtr);
}
/*  These internal functions implements a frozen namespace for extracting
attributes from the antelope Trace database.  Originally I passed the output
of these function (two MetadataList structures containing list of attributes
to be extracted for ensemble and each trace) I realized that the namespace
was fixed by the Trace schema so this seemed an unnecessary burden for the
interface.  It makes the interface definition less general, but for the time
being there is not sensible alternative to the Antelope interface for 
continuous data anyway.  Hence, I'll simply the interface and freeze these
names.  

Note this DOES still require a Trace (4.0 at this writing) schema mapping
operation to create the AttributeMap object inside the constructor below.  
The names in that parameter file MUST match the ones loaded inline here.
*/
MetadataList BuildEnsembleMDL()
{
	MetadataList mdl;
/*
	Metadata_typedef entry;
	entry.tag="evid";
	entry.mdt=MDint;
	mdl.push_back(entry);
*/
	return(mdl);
}
MetadataList BuildStationMDL()
{
	MetadataList mdl;
	Metadata_typedef entry;
	// This list is the bare minimum.  Others are extracted using
	// database functions below
	entry.tag="sta";
	entry.mdt=MDstring;
	mdl.push_back(entry);
	entry.tag="chan";
	entry.mdt=MDstring;
	mdl.push_back(entry);
	entry.tag="time";
	entry.mdt=MDreal;
	mdl.push_back(entry);
	entry.tag="endtime";
	entry.mdt=MDreal;
	mdl.push_back(entry);
	entry.tag="nsamp";
	entry.mdt=MDint;
	mdl.push_back(entry);
	entry.tag="samprate";
	entry.mdt=MDreal;
	mdl.push_back(entry);
	entry.tag="calib";
	entry.mdt=MDreal;
	mdl.push_back(entry);
	entry.tag="datatype";
	entry.mdt=MDstring;
	mdl.push_back(entry);
	entry.tag="segtype";
	entry.mdt=MDstring;
	mdl.push_back(entry);
	return(mdl);
}
TimeSeriesEnsemble::TimeSeriesEnsemble(DatabaseHandle& dbhi,
	TimeWindow twin,
		const string sta_expression,
			const string chan_expression,
	bool require_coords,
		bool require_orientation,
			bool require_response)
{

	AttributeMap am("Trace4.0");  //Defines namespace for trace database
	int i,j;
	const string base_error_message("TimeSeriesEnsemble TimeWindow driven database constructor: ");
	DatascopeHandle dbhandle=dynamic_cast<DatascopeHandle&>(dbhi);
	int ierr;
	Dbptr dbtr; // Trace database pointer
	dbtr.database= -1;
	// Interface variables to use Danny Harvey's routine
	// with no changes.  Necessary for preference of strings
	// and boolean rather than char * and int
	//
	int orient,ir, coords;
	char *net_expr,*sta_expr,*chan_expr;
	net_expr=NULL;  //interface.  Always ignored here.
	// For sta and chan we need to convert from strings
	// to char * with this because of the way NULL is used
	// to signal none to Danny's routines.
	if(sta_expression=="none")
		sta_expr=NULL;
	else
		sta_expr=strdup(sta_expression.c_str());
	if(chan_expression=="none")
		chan_expr=NULL;
	else
		chan_expr=strdup(chan_expression.c_str());
	if(require_coords)
		coords=1;
	else
		coords=0;
	if(require_orientation)
		orient=1;
	else
		orient=0;
	if(require_response)
		ir=1;
	else
		ir=0;
	Dbptr dbsc,dbscgr;

	// now call Danny Harvey's station-channel C function
	ierr=grdb_sc_loadcss(dbhandle.db,
		net_expr,sta_expr,chan_expr,
		twin.start,twin.end,
		coords,ir,orient,&dbscgr,&dbsc);
	if(ierr!=0)
	{
		clear_register(1);   
		free(sta_expr);
		free(chan_expr);
		throw SeisppError(base_error_message
			+string("grdb_sc_loadcss procedure failed\n"));
	}

	char *gap="seg";
	// call Danny Harvey's routine that creates a trace
	// database using the result of the grdb_sc_loadcss function.
	// We always ask it to apply calib and always ask it to 
	// handle data with gaps.  (set with gap variable).
	//
	ierr=grtr_sc_create(dbsc,net_expr,sta_expr,chan_expr,
		twin.start,twin.end,
		gap,1,ir,&dbtr);
	if(ierr!=0)
	{
		clear_register(1);   
		free(sta_expr);
		free(chan_expr);
		throw SeisppError(base_error_message
			+string("grdb_sc_create procedure failed\n"));
	}

	free(sta_expr);
	free(chan_expr);

	int ntraces;
	dbquery(dbtr,dbRECORD_COUNT,&ntraces);
	if(ntraces<=0) 
	{
		trdestroy(&dbtr);
		throw SeisppError(base_error_message
		   +string("no data in temporary trace database\n"));
	}
	try {
		DatascopeHandle dbtr_handle;
		dbtr_handle.db=dbtr;
		// 
		// At the moment we do a hidden trick here.  We will extract the ensemble metadata fromn
		// the trace event table.  This is very schema specific, but pretty much unavoidable.
		// I think it undesirable to clutter the interface with this detail so I'll just hard
		// wire this in assuming that any use of this function implies a css parent schema 
		// anyway.  
		//
		dbtr_handle.lookup("event");
		dbtr_handle.rewind();  // probably unnecessary, but can't hurt
		MetadataList ensemble_mdl=BuildEnsembleMDL();
		Metadata mdens(dynamic_cast<DatabaseHandle&>(dbtr_handle),
			ensemble_mdl,am);
		// This maybe should be an auto_ptr but I've had confusing results with Sun's compilere
		
		dbtr_handle.lookup("trace");
		dbtr_handle.rewind();
		// 
		// For now the ensemble Metadata, mdens, is empty.
		// If at a later date this changes, we need a routine
		// that copies the data defined by BuildEnsembleMDL from
		// mdens to the metadata area of this ensemble.
		// Here is a commented out prototype:
		//
		// LoadEnsembleMetadata(this,mdens);
		// 
		// First we have to sort the trace database by sta:chan:time
		// and group it by sta:chan.  This will allow us to easily
		// detect and process gaps.
		//
		list<string> sortkeys,groupkeys;
		sortkeys.push_back("sta");
		sortkeys.push_back("chan");
		sortkeys.push_back("time");
		dbtr_handle.sort(sortkeys);
		DatascopeHandle dbtrgrp=dbtr_handle;

		groupkeys.push_back("sta");
		groupkeys.push_back("chan");
		dbtrgrp.group(groupkeys);
		dbtrgrp.rewind();
		MetadataList data_mdl=BuildStationMDL();
		// Conservative number to reserve, but this will
		// improve efficiency
		member.reserve(dbtrgrp.number_tuples());
		
		for(int irec=0;irec<dbtrgrp.number_tuples();++irec,++dbtrgrp)
		{
			// Enter the arcain world of Datascope group
			// pointers.  Because dbtr_handle is the parent 
			// of dbtrgrp we use dbget_range to find the 
			// range of rows to process for one sta:chan 
			// Normally the count of that result is one, but
			// when it is greater than one we know we have 
			// a gap problem to deal with.
			//
			Dbptr db_bundle;
			int is,ie;
			char sta[10],chan[10];  // We'll need to have these sometimes
			dbgetv(dbtrgrp.db,0,
				"sta",sta,"chan",chan,"bundle",&db_bundle,0);
			dbget_range(db_bundle,&is,&ie);
			// For either case we assume we can get the
			// main required attributes from the first
			// trace entry.  The only thing that should
			// differ between segments are time fields so
			// this should be more than ok.
			dbtr_handle.db.record=is;
			Metadata trattributes(dbtr_handle,data_mdl,am);
			// These attributes are loaded conditionally
			if(require_coords)
			{
				double lat,lon,elev,dnorth,deast;
				char refsta[30];
				if(dbgetv(dbtr_handle.db,0,
					"lat",&lat,
					"lon",&lon,
					"elev",&elev,
					"dnorth",&dnorth,
					"deast",&deast,
					"refsta",refsta,
					0) == dbINVALID)
				{
					throw SeisppError(base_error_message
					 + string(" dbgetv error reading trace table coordinate attributes"));
				}
				trattributes.put("lat",lat);
				trattributes.put("lon",lon);
				trattributes.put("elev",elev);
				trattributes.put("dnorth",dnorth);
				trattributes.put("deast",deast);
				trattributes.put("refsta",refsta);
			}
			if(require_orientation)
			{
				double hang, vang;
				if(dbgetv(dbtr_handle.db,0,
					"hang",&hang,
					"vang",&vang,
					0) == dbINVALID)
				{
					throw SeisppError(base_error_message
					 + string(" dbgetv error reading trace table orientation attributes"));
				}
				trattributes.put("hang",hang);
				trattributes.put("vang",vang);
				
			}
			if(require_response)
			{
				cerr << base_error_message
					<<" WARNING "
					<< "  request to load response information ignored."
					<< endl
					<< "Feature not yet implemented" << endl;
			}


			// This loads attributes but not data
			TimeSeries seis(trattributes,false);
			seis.ns=static_cast<int>((twin.end-twin.start)/seis.dt);
			seis.s.reserve(seis.ns);
			Trsample *tdata;

			if((ie-is)==1)
			{
				// Block for no gaps
				dbgetv(dbtr_handle.db,0,"data",&tdata,
					"nsamp",&(seis.ns),0);
				for(i=0;i<seis.ns;++i)
				{
					seis.s.push_back(static_cast<double>(tdata[i]));
				}
			}
			else
			{
cout << "TimeSeriesEnsemble continuous data constructor:  "
	<< sta << ":"<<chan
	<<" has multiple segments = "<<ie-is<<endl
	<< "Gaps will be flagged and zeroed"<<endl;
				// land here if there are gaps in this
				// time interal.
				int ns_this_segment;
				double t0_this_segment;
				double etime_this_segment;
				double etime_last_segment;
				double tprime;
				// Initialize contents so we can just leave gaps 0
				for(i=0;i<seis.ns;++i) seis.s.push_back(0.0);
				for(i=is;i<ie;++i)
				{
					dbtr_handle.db.record=i;
					dbgetv(dbtr_handle.db,0,"data",&tdata,
						"nsamp",&ns_this_segment,
						"time",&t0_this_segment,
						"endtime",&etime_this_segment,
						0);
					if(i==is)
					{
						// test for gap at t0
						if((t0_this_segment-twin.start)
							> seis.dt)
						{
							seis.add_gap(TimeWindow(
								twin.start,
								t0_this_segment));
						}
					}
					// Similar for endtime
					else if(i==(ie-1))
					{
						seis.add_gap(TimeWindow(
							etime_last_segment,
							t0_this_segment));
						// test for end gap
						if( (twin.end-etime_this_segment)
							> seis.dt)
						{
							seis.add_gap(TimeWindow(
								etime_this_segment,
								twin.end));
						}
						for(int k=0;k<ns_this_segment;++k)
						{
							tprime=t0_this_segment
								+ seis.dt
								*static_cast<double>(k);
							if(tprime>(twin.end+0.5*seis.dt))
							{
								seis.ns=seis.sample_number(tprime) - 1;
								break;
							}
								
					
							seis.s[seis.sample_number(tprime)]
								= static_cast<double>(tdata[k]);
								
						}
					}
					else
					{
						seis.add_gap(TimeWindow(
							etime_last_segment,
							t0_this_segment));
					}
					// In all cases we just copy into
					// this container

					for(int k=0;k<ns_this_segment;++k)
					{
						tprime=t0_this_segment
							+ seis.dt
							*static_cast<double>(k);
						seis.s[seis.sample_number(tprime)]
							= static_cast<double>(tdata[k]);
							
					}
					etime_last_segment=etime_this_segment;
				}
			}

			seis.live=true;
			seis.ns=seis.s.size();
			//
			// Push these into the ensemble
			//
			member.push_back(seis);
		}
		trdestroy(&dbtr);
	} catch (...)
	{
		trdestroy(&dbtr);
		throw;
	}
}

// Partial copy constructor copies metadata only.  reserves nmembers slots
// in ensemble container
TimeSeriesEnsemble::TimeSeriesEnsemble(Metadata& md,int nmembers)
	: Metadata(md)
{
	member.reserve(nmembers);
}
	
ThreeComponentEnsemble::ThreeComponentEnsemble()
{
	member.reserve(0);
}
ThreeComponentEnsemble::ThreeComponentEnsemble(int nstations, int nsamples)
{
	member.reserve(nstations);
	for(int i=0;i<nstations;++i)
	{
		ThreeComponentSeismogram *tcs 
			= new ThreeComponentSeismogram(nsamples);
		member.push_back(*tcs);
		delete tcs;
	}
}
ThreeComponentEnsemble::ThreeComponentEnsemble(int nstations, 
		int nsamples,
			MetadataList& mdl)
{
	member.reserve(nstations);
	for(int i=0;i<nstations;++i)
	{
		ThreeComponentSeismogram *tcs 
			= new ThreeComponentSeismogram(nsamples);
		member.push_back(*tcs);
		delete tcs;
	}
}
/* Database-driven constructor for an ensemble.  This implementation uses
a Datascope database only through an immediate dynamic_cast to a 
DatascopeHandle, but the idea is that a more generic interface 
would change nothing in the calling sequence.

station_mdl and ensemble_mdl determine which metadata are extracted 
from the database for individual stations in the ensemble and 
as the global metadata for the ensemble respectively.   The 
station metadata is derived from the ThreeComponentSeismogram 
constructor, but the global metadata is arbitrarily extracted from
the first row of the view forming the requested ensemble.  This 
tacitly assumes then that all rows in view that forms this ensemble
have the same attributes (i.e. these are common attributes obtained
through some form of relational join.)  

The routine will pass along any exceptions thrown by functions 
called by the constructor.  It will also throw a SeisppDberror 
in cases best seen by inspecting the code below.

Author:  Gary L. Pavlis
Written:  July 2004
*/
ThreeComponentEnsemble::ThreeComponentEnsemble(DatabaseHandle& rdb,
	MetadataList& station_mdl,
        	MetadataList& ensemble_mdl,
        		AttributeMap& am)
{
	int i;
	int nsta;
	const string this_function_base_message("ThreeComponentEnsemble database constructor");
	ThreeComponentSeismogram *data3c;
	DatascopeHandle& dbh=dynamic_cast<DatascopeHandle&>(rdb);
	try {
		// Will throw an exception if this isn't a group pointer
		DBBundle ensemble_bundle=dbh.get_range();
		nsta = ensemble_bundle.end_record-ensemble_bundle.start_record;
		// We need a copy of this pointer 
		Dbptr dbparent=ensemble_bundle.parent;
		--dbparent.table;
		DatascopeHandle dbhv(ensemble_bundle.parent,
			dbparent);
		// Necessary because the ThreeComponentSeismogram
		// constructor uses a generic handle
		DatabaseHandle *rdbhv=dynamic_cast
			<DatabaseHandle *>(&dbhv);
		// Loop over members
		for(i=0,dbhv.db.record=ensemble_bundle.start_record;
			dbhv.db.record<ensemble_bundle.end_record;
			++i,++dbhv.db.record)
		{
			try {
				data3c = new ThreeComponentSeismogram(*rdbhv,
					station_mdl,am);
			} catch (SeisppDberror dberr)
			{
				cerr << "Problem with member "
					<< i 
					<< " in ensemble construction" << endl;
				dberr.log_error();
				cerr << "Data for this member skipped" << endl;
				continue;
			}
			catch (MetadataError& mderr)
			{
				mderr.log_error();
				throw SeisppError(string("Metadata problem"));
			}
			member.push_back(*data3c);
			delete data3c;
			// copy global metadata only for the first 
			// row in this view
			if(i==0)
			{
				DatascopeHandle dbhvsta;
				if(dbhv.is_bundle)
				{
					DBBundle sta_bundle=dbhv.get_range();
					dbhvsta=DatascopeHandle(
						sta_bundle.parent,
						sta_bundle.parent);
					dbhvsta.db.record=sta_bundle.start_record;
				}
				else
				{
					dbhvsta=dbhv;
				}
				Metadata ens_md(dynamic_cast<DatabaseHandle&>(dbhvsta),
					ensemble_mdl,am);
				copy_selected_metadata(ens_md,
					dynamic_cast<Metadata&>(*this),
					ensemble_mdl);
			}
		}

	} catch (...) { throw;};
}
//copy constructor 
ThreeComponentEnsemble::ThreeComponentEnsemble(const ThreeComponentEnsemble& tceold)
	: Metadata(tceold)
{
	int nmembers=tceold.member.size();
	if(!member.empty()) member.clear();
	member.reserve(nmembers);
	for(int i=0; i<nmembers; ++i)
		member.push_back(tceold.member[i]);
}
// Partial copy constructor copies metadata only.  reserves nmembers slots
// in ensemble container
ThreeComponentEnsemble::ThreeComponentEnsemble(Metadata& md,int nmembers)
	: Metadata(md)
{
	member.reserve(nmembers);
}

/* Ensemble assignment operators.

A maintenance issue is that most functions contain a pfdup 
call.  This is a hidden method to clone the Metadata connected
to that object.  The problem is if the Metadata implementation
changes this will break this code.
*/


//
// assignment operators for ensemble objects (could maybe be templated)
//
TimeSeriesEnsemble& TimeSeriesEnsemble::operator=(const TimeSeriesEnsemble& tseold)
{
	if(this!=&tseold)
	{
		if(pf!=NULL) pffree(pf);
		pf = pfdup(tseold.pf);
		if(!(this->member.empty())) this->member.clear();
		int nmembers=tseold.member.size();
		member.reserve(nmembers);
		for(int i=0; i<nmembers; ++i)
			member.push_back(tseold.member[i]);
	}
	return(*this);
}
ThreeComponentEnsemble& ThreeComponentEnsemble::operator=(const ThreeComponentEnsemble& tseold)
{
	if(this!=&tseold)
	{
		if(pf!=NULL) pffree(pf);
		pf = pfdup(tseold.pf);
		if(!(this->member.empty())) this->member.clear(); 
		int nmembers=tseold.member.size();
		member.reserve(nmembers);
		for(int i=0; i<nmembers; ++i)
			member.push_back(tseold.member[i]);
	}
	return(*this);
}
} // Termination of namespace SEISPP definitions