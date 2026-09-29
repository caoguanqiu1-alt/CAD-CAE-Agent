using System;
using System.IO;
using System.Linq;
using System.Collections.Generic;
using SolidWorks.Interop.sldworks;
using SolidWorks.Interop.cosworks;

partial class SimulationBridge
{
    static ICWStudy ExistingStudy(ISldWorks app,Dictionary<string,object> p)
    {
        var diag=D();var cw=Cosmos(app,p,diag);Require(cw!=null,"SIMULATION_API_UNAVAILABLE");
        var doc=Keep((ICWModelDoc)Call("Simulation.ActiveDoc",()=>cw.ActiveDoc));Require(doc!=null,"SIMULATION_NO_ACTIVE_DOCUMENT");
        var manager=Keep((ICWStudyManager)doc.StudyManager);string name=Arg(p,"study");
        for(int i=0;i<manager.StudyCount;i++){var s=Keep((ICWStudy)manager.GetStudy(i));if(s.Name==name){Require(s.AnalysisType==0,"STUDY_NOT_STATIC");manager.ActiveStudy=i;return s;}}
        throw new InvalidOperationException("STUDY_NOT_FOUND");
    }
    static ICWSolidBody SingleBody(ICWStudy study)
    {
        var mgr=Keep((ICWSolidManager)study.SolidManager);Require(mgr.ComponentCount==1,"SINGLE_COMPONENT_REQUIRED");int err=0;
        var comp=Keep((ICWSolidComponent)Call("SolidManager.GetComponentAt",()=>mgr.GetComponentAt(0,out err)));Require(err==0&&comp!=null,"COMPONENT_ERROR");
        Require(comp.SolidBodyCount==1,"SINGLE_SOLID_BODY_REQUIRED");
        var body=Keep((ICWSolidBody)Call("SolidComponent.GetSolidBodyAt",()=>comp.GetSolidBodyAt(0,out err)));Require(err==0&&body!=null,"SOLID_BODY_ERROR");return body;
    }
    static Dictionary<string,object> MaterialData(ICWSolidBody body)
    {
        var mat=Keep((ICWMaterial)Call("GetSolidBodyMaterial",()=>body.GetSolidBodyMaterial()));Require(mat!=null,"MATERIAL_NOT_DEFINED");int temp=0;
        double ex=Call("Material.EX(SI)",()=>mat.GetPropertyByName(0,"EX",out temp));
        double nu=Call("Material.NUXY(SI)",()=>mat.GetPropertyByName(0,"NUXY",out temp));
        double yield=Call("Material.SIGYLD(SI)",()=>mat.GetPropertyByName(0,"SIGYLD",out temp));
        Require(ex>0 && nu>-1 && nu<0.5,"MATERIAL_PROPERTIES_INVALID");
        return D("material",mat.MaterialName,"model_type",mat.ModelType,"elastic_modulus_Pa",ex,"poisson_ratio",nu,"yield_strength_MPa",yield/1e6);
    }
    static object FaceById(IModelDoc2 model,string id)
    {
        Require(id.StartsWith("face_"),"FACE_ID_REQUIRED");int error=0;var bytes=Convert.FromBase64String(id.Substring(5));
        var obj=Keep(Call("ResolveFace",()=>model.Extension.GetObjectByPersistReference3(bytes,out error)));
        Require(error==0&&obj is IFace2,"INVALID_FACE_REFERENCE");return obj;
    }
    static List<object> BoundaryState(ICWLoadsAndRestraintsManager mgr)
    {
        var rows=new List<object>();for(int i=0;i<mgr.Count;i++){int err=0;var b=Keep((ICWLoadsAndRestraints)mgr.GetLoadsAndRestraints(i,out err));Require(err==0,"BOUNDARY_READ_FAILED");rows.Add(D("name",b.Name,"type",b.Type,"state",b.State,"entity_count",b.EntityCount));}return rows;
    }
    static Dictionary<string,object> Phase2(ISldWorks app,Dictionary<string,object> p)
    {
        var model=Model(app,p);var study=ExistingStudy(app,p);var lm=Keep((ICWLoadsAndRestraintsManager)study.LoadsAndRestraintsManager);
        string op=Arg(p,"operation");var d=D("status","success","study",study.Name);
        if(op=="phase2_state") {d["boundaries"]=BoundaryState(lm);var mesh=Keep((ICWMesh)study.Mesh);d["mesh_state"]=mesh.MeshState;d["node_count"]=mesh.NodeCount;d["element_count"]=mesh.ElementCount;d["result_folder"]=Keep((ICWStaticStudyOptions)study.StaticStudyOptions).ResultFolder;d["dirty"]=model.GetSaveFlag();try{d["material"]=MaterialData(SingleBody(study));}catch(Exception ex){d["material_diagnostic"]=ex.Message;}return d;}
        if(op=="phase2_material") {
            string library=Arg(p,"library"),name=Arg(p,"material");Require(File.Exists(library),"MATERIAL_LIBRARY_MISSING");Require(!String.IsNullOrWhiteSpace(name),"MATERIAL_NAME_REQUIRED");
            var body=SingleBody(study);var mat=Keep((ICWMaterial)body.GetSolidBodyMaterial());int error=0;
            bool alreadyAssigned=mat!=null&&mat.MaterialName==name;d["reused_existing_library_material"]=alreadyAssigned;MutationStarted=true;
            if(!alreadyAssigned){error=Call("SetLibraryMaterial",()=>body.SetLibraryMaterial(library,name));d["library_return_code"]=error;mat=Keep((ICWMaterial)body.GetSolidBodyMaterial());}
            // SW2020 can return 1 even after the requested material is assigned.
            // Accept only an exact name readback, never silently choose defaults.
            Require(mat!=null&&mat.MaterialName==name,"MATERIAL_LIBRARY_MATCH_FAILED: "+error);
            int libraryModel=mat.ModelType;mat.ModelType=(int)swsMaterialModelType_e.swsMaterialModelTypeLinearElasticIsotropic;
            error=Call("SetSolidBodyMaterial(linear elastic)",()=>body.SetSolidBodyMaterial((CWMaterial)mat));Require(error==0,"MATERIAL_SET_FAILED: "+Enum.GetName(typeof(swsMaterialErrorWarning_e),error));
            d["properties"]=MaterialData(body);d["source_library_model_type"]=libraryModel;d["library"]=library;return d;
        }
        if(op=="phase2_fixture") {
            Require(lm.Count==0,"BOUNDARY_ALREADY_EXISTS: inspect before retry");var face=FaceById(model,Arg(p,"face"));int err=0;MutationStarted=true;
            var fixture=Keep((ICWRestraint)Call("AddRestraint(Fixed)",()=>lm.AddRestraint((int)swsRestraintType_e.swsRestraintTypeFixed,new object[]{face},null,out err)));
            Require(err==0&&fixture!=null,"FIXTURE_FAILED: "+err);Require(fixture.RestraintType==0&&lm.Count==1,"FIXTURE_READBACK_FAILED");d["boundaries"]=BoundaryState(lm);d["fixed_face"]=Arg(p,"face");return d;
        }
        if(op=="phase2_force") {
            Require(lm.Count==1,"EXPECTED_ONE_FIXTURE: inspect before adding force");double force=Convert.ToDouble(p["magnitude_N"]);Require(force>0 && !Double.IsInfinity(force),"INVALID_FORCE");
            var face=FaceById(model,Arg(p,"face"));
            IFeature reference=null;IRefPlane plane=null;
            foreach(string name in new[]{"Right Plane","右视基准面","右視基準面"}){reference=Keep((IFeature)((IPartDoc)model).FeatureByName(name));if(reference!=null){plane=Keep((IRefPlane)reference.GetSpecificFeature2());break;}}
            Require(reference!=null&&plane!=null,"RIGHT_PLANE_NOT_FOUND");
            var util=Keep((IMathUtility)app.GetMathUtility());var v=Keep((IMathVector)util.CreateVector(new double[]{0,0,1}));var transform=Keep(plane.Transform);
            var normal=Numbers(Keep((IMathVector)v.MultiplyTransform(transform)).ArrayData);Require(Math.Abs(Math.Abs(normal[0])-1)<1e-8&&Math.Abs(normal[1])<1e-8&&Math.Abs(normal[2])<1e-8,"REFERENCE_NOT_GLOBAL_X");
            // Select exact reference feature through API, then use the API-selected object.
            model.ClearSelection2(true);Require(reference.Select2(false,0),"REFERENCE_SELECTION_FAILED");
            var sm=Keep((ISelectionMgr)model.SelectionManager);var direction=Keep(sm.GetSelectedObject6(1,-1));Require(direction!=null,"REFERENCE_SELECTION_EMPTY");
            model.ClearSelection2(true);int error=0;MutationStarted=true;
            var load=Keep((ICWForce)Call("AddForce3(+global X, uniform total N)",()=>lm.AddForce3(0,0,2,0,0,0,new double[0],new double[0],false,false,0,0,4,0,new double[]{1,1,force*normal[0]},false,false,new object[]{face},direction,false,out error)));
            Require(error==0&&load!=null,"FORCE_FAILED: "+Enum.GetName(typeof(swsForceError_e),error));
            int x=0,y=0,z=0;double fx=0,fy=0,fz=0;Call("GetForceComponentValues",()=>{load.GetForceComponentValues(out x,out y,out z,out fx,out fy,out fz);return true;});
            Require(load.Unit==0&&Math.Abs(fz-force*normal[0])<1e-8&&lm.Count==2,"FORCE_READBACK_FAILED");
            d["force_units"]=load.Unit;d["reference_plane_normal_global"]=normal;d["reference_component_flags"]=new[]{x,y,z};d["reference_components_N"]=new[]{fx,fy,fz};d["global_force_N"]=new[]{force,0.0,0.0};d["boundaries"]=BoundaryState(lm);return d;
        }
        if(op=="phase2_mesh") {
            MaterialData(SingleBody(study));Require(lm.Count>=2,"BOUNDARIES_REQUIRED");double size=Convert.ToDouble(p["element_size_mm"]);Require(size>0&&size<=20,"INVALID_MESH_SIZE");
            var mesh=Keep((ICWMesh)study.Mesh);mesh.Quality=(int)swsMeshQuality_e.swsMeshQualityHigh;mesh.MesherType=0;MutationStarted=true;
            int error=Call("CreateMesh(mm)",()=>study.CreateMesh((int)swsLinearUnit_e.swsLinearUnitMillimeters,size,size/20));
            d["mesh_error"]=error;d["mesh_error_name"]=Enum.GetName(typeof(swsStudyMeshError_e),error);Require(error==0,"MESH_FAILED: "+d["mesh_error_name"]);
            d["node_count"]=mesh.NodeCount;d["element_count"]=mesh.ElementCount;d["quality"]=mesh.Quality;d["element_size_mm"]=size;d["tolerance_mm"]=size/20;return d;
        }
        if(op=="phase2_run") {
            d["material"]=MaterialData(SingleBody(study));Require(lm.Count>=2,"BOUNDARIES_REQUIRED");var mesh=Keep((ICWMesh)study.Mesh);Require(mesh.NodeCount>0&&mesh.ElementCount>0,"MESH_REQUIRED");
            string folder=Arg(p,"results_folder");Require(Path.IsPathRooted(folder),"ABSOLUTE_RESULTS_FOLDER_REQUIRED");Directory.CreateDirectory(folder);
            var options=Keep((ICWStaticStudyOptions)study.StaticStudyOptions);
            Require(String.Equals(Path.GetFullPath(options.ResultFolder).TrimEnd('\\','/'),Path.GetFullPath(folder).TrimEnd('\\','/'),StringComparison.OrdinalIgnoreCase),"RESULT_FOLDER_MISMATCH: use the existing mesh folder; changing it after meshing can return zero without results");
            options.LargeDisplacement=0;options.UseSoftSpring=0;options.UseInertialRelief=0;options.ComputeFreeBodyForce=1;
            MutationStarted=true;int error=Call("RunAnalysis",()=>study.RunAnalysis());d["solver_error_code"]=error;d["solver_error_name"]=Enum.GetName(typeof(swsRunAnalysisError_e),error)??"UNKNOWN_SOLVER_ERROR";
            if(error!=0){d["status"]="error";d["error_code"]=error==22?"SIMULATION_LICENSE_UNAVAILABLE":"SOLVER_FAILED";return d;}
            var solved=Keep((ICWResults)study.Results);Require(solved!=null,"SOLVER_NO_RESULTS: return code zero alone is insufficient");
            int resultsError=0;var checkValues=Numbers(Call("VerifySolvedDisplacement",()=>solved.GetMinMaxDisplacement(3,1,null,0,out resultsError)));Require(resultsError==0&&checkValues.Length==4,"SOLVER_RESULTS_NOT_READABLE");
            d["max_displacement_mm"]=checkValues[3];d["simulation_license_status"]="static_solve_and_results_succeeded";d["results_folder"]=options.ResultFolder;return d;
        }
        if(op=="phase2_results") {
            var results=Keep((ICWResults)study.Results);Require(results!=null,"RESULTS_UNAVAILABLE");int error=0;
            var values=Numbers(Call("GetMinMaxDisplacement(URES,mm)",()=>results.GetMinMaxDisplacement(3,1,null,0,out error)));Require(error==0&&values.Length==4,"DISPLACEMENT_RESULTS_FAILED: "+error);
            d["min_displacement_mm"]=values[1];d["max_displacement_mm"]=values[3];d["min_node"]=values[0];d["max_node"]=values[2];
            var mesh=Keep((ICWMesh)study.Mesh);double x=0,y=0,z=0;int locError=Call("GetNodeLocation(max displacement)",()=>mesh.GetNodeLocation((int)values[2],out x,out y,out z));d["max_location_raw_m"]=new[]{x,y,z};d["max_location_mm"]=new[]{x*1000,y*1000,z*1000};d["location_error"]=locError;
            var stress=Numbers(Call("GetMinMaxStress(von Mises,MPa)",()=>results.GetMinMaxStress(9,0,1,null,3,out error)));Require(error==0&&stress.Length==4,"STRESS_RESULTS_FAILED: "+error);d["max_von_mises_MPa"]=stress[3];
            var material=MaterialData(SingleBody(study));d["material"]=material;d["calculated_safety_factor"]=Convert.ToDouble(material["yield_strength_MPa"])/stress[3];
            if(p.ContainsKey("fixed_face")){var face=FaceById(model,Arg(p,"fixed_face"));object combined=null,selected=null;
                var raw=Call("GetReactionForcesAndMomentsWithSelections",()=>results.GetReactionForcesAndMomentsWithSelections(1,null,0,new object[]{face},out combined,out selected,out error));
                d["reaction_error"]=error;if(error==0){d["selected_reaction_N_Nm"]=Numbers(selected);d["combined_reaction_N_Nm"]=Numbers(combined);d["nodal_reaction_value_count"]=((Array)raw).Length;}
            }
            d["node_count"]=mesh.NodeCount;d["element_count"]=mesh.ElementCount;d["plot_names"]=Objects(results.GetPlotNames());return d;
        }
        if(op=="phase2_plot") {
            string path=Arg(p,"output_bmp");Require(Path.IsPathRooted(path)&&!File.Exists(path),"NEW_ABSOLUTE_IMAGE_PATH_REQUIRED");
            var results=Keep((ICWResults)study.Results);Require(results!=null,"RESULTS_UNAVAILABLE");int error=0;MutationStarted=true;
            var plot=Keep((ICWPlot)Call("CreatePlot(URES,mm)",()=>results.CreatePlot(1,3,0,false,out error)));Require(error==0&&plot!=null,"PLOT_CREATE_FAILED: "+error);
            // 2020 SP5 CreatePlot can show Angstrom despite NUnits=0.
            // Explicitly set and read back units before labeling/exporting.
            Require(Call("Plot.SetComponentUnitAndValueByElem(URES,mm)",()=>plot.SetComponentUnitAndValueByElem(3,0,false))==0,"PLOT_UNITS_FAILED");
            var plotValues=Numbers(plot.GetMinMaxResultValues(out error));Require(error==0,"PLOT_EXTREMA_UNAVAILABLE");
            var resultValues=Numbers(results.GetMinMaxDisplacement(3,1,null,0,out error));Require(error==0&&plotValues.Length==4&&Math.Abs(plotValues[3]-resultValues[3])<1e-9,"PLOT_UNITS_READBACK_FAILED");
            int code=Call("Plot.ShowDeformedPlot(true scale)",()=>plot.ShowDeformedPlot(true,(int)swsDeformType_e.swsTrueScale,1,true));Require(code==0,"PLOT_SETTINGS_FAILED: "+code);
            Require(plot.SetPlotTitle(Arg(p,"title","URES (mm) - 1000 N axial tension - true scale"))==0,"PLOT_TITLE_FAILED");
            Require(Call("Plot.ActivatePlot",()=>plot.ActivatePlot())==0,"PLOT_ACTIVATION_FAILED");
            model.ClearSelection2(true);model.ShowNamedView2("",7);model.ViewZoomtofit2();model.GraphicsRedraw2();
            Require(Call("SaveBMP(displacement plot)",()=>model.SaveBMP(path,1800,1100)),"PLOT_IMAGE_FAILED");
            string name="";plot.GetPlotName(out name);d["plot"]=name;d["output_bmp"]=path;d["displacement_scale"]=1;d["units"]="mm";return d;
        }
        if(op=="phase2_view") {
            foreach(string name in new[]{"草图1","草图2"}){var f=Keep((IFeature)((IPartDoc)model).FeatureByName(name));if(f!=null&&f.GetTypeName2()=="ProfileFeature"){model.ClearSelection2(true);Require(f.Select2(false,0),"SKETCH_DISPLAY_SELECTION_FAILED");model.BlankSketch();}}
            model.ClearSelection2(true);var results=Keep((ICWResults)study.Results);Require(results!=null&&results.ActivatePlot(Arg(p,"plot_name")),"EXISTING_PLOT_ACTIVATION_FAILED");
            int plotErr=0;var plot=Keep((ICWPlot)results.GetPlot(Arg(p,"plot_name"),out plotErr));Require(plotErr==0&&plot!=null,"PLOT_GET_FAILED");
            d["set_unit_result"]=plot.SetComponentUnitAndValueByElem(3,0,false);d["plot_extrema"]=Numbers(plot.GetMinMaxResultValues(out plotErr));d["plot_extrema_error"]=plotErr;
            plot.ActivatePlot();
            model.ShowNamedView2("",7);model.ViewZoomtofit2();model.GraphicsRedraw2();d["plot"]=Arg(p,"plot_name");return d;
        }
        throw new InvalidOperationException("UNKNOWN_PHASE2_OPERATION");
    }
}
