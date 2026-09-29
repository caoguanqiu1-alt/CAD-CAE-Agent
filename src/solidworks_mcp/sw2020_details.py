"""Bounded finishing operations: real SW2020 geometry inspection and edge details."""
from .sw2020_workflow import real_adapter, model_state, methods, geometry

def register_details(server):
    @server.mcp.tool()
    async def sw2020_details(expected_document: str, operation: str,
                             edge_points_mm: list[list[float]] = [], radius_mm: float = 3,
                             thread_diameter_mm: float = 10, thread_depth_mm: float = 14,
                             note: str = '', feature_name: str = '') -> dict:
        """Inspect cylinders/edges, fillet exact nearby edges, add cosmetic thread,
        hide planes, or write material specification metadata. No GUI automation.
        Points are model-space millimetres, matched within 0.05 mm to actual edges.
        Cosmetic thread is not a helical solid. Inspect after any failure.
        """
        adapter=real_adapter(server)
        model,state=model_state(adapter,expected_document)
        if not expected_document or model is None or state['type']!=1 or state['sketch_editing']:
            raise ValueError('Need named active Part outside sketch editing')
        if operation=='material_note':
            props=methods(model.Extension.CustomPropertyManager(''),'Add3')
            code=props.Add3('Material specification',30,note,1)
            return {'status':'success','material_specification':note,'result_code':code,'physical_material_assigned':False}
        if operation=='hide_planes':
            model.ClearSelection2(True)
            methods(model,'FirstFeature','BlankRefGeom')
            feat=model.FirstFeature()
            count=0
            while feat is not None:
                methods(feat,'GetTypeName2','Select2','GetNextFeature')
                if feat.GetTypeName2()=='RefPlane':feat.Select2(True,0);count+=1
                feat=feat.GetNextFeature()
            model.BlankRefGeom()
            model.ClearSelection2(True)
            return {'status':'success','hidden_planes':count}
        bodies=list(model.GetBodies2(0,False) or [])
        edges=[]
        cylinders=[]
        for body in bodies:
            methods(body,'GetEdges','GetFaces')
            edges.extend(body.GetEdges() or [])
            if operation=='inspect':
                for face in body.GetFaces() or []:
                    methods(face,'GetSurface')
                    surf=methods(face.GetSurface(),'IsCylinder')
                    if surf.IsCylinder():cylinders.append(list(surf.CylinderParams))
        if operation=='inspect':
            rows=[]
            for i,edge in enumerate(edges):
                methods(edge,'GetCurve','GetStartVertex','GetEndVertex')
                curve=methods(edge.GetCurve(),'IsCircle')
                row={'index':i}
                if curve.IsCircle():row['circle_m']=list(curve.CircleParams)
                vertices=[]
                for vertex in [edge.GetStartVertex(),edge.GetEndVertex()]:
                    if vertex is not None:
                        methods(vertex,'GetPoint')
                        vertices.append([v*1000 for v in vertex.GetPoint()])
                row['vertices_mm']=vertices
                rows.append(row)
            return {'status':'success',**geometry(model),'cylinders_m':cylinders,'edges':rows}
        if operation not in ['fillet','thread'] or not edge_points_mm:
            raise ValueError('Expected inspect/fillet/thread/hide_planes/material_note')
        if radius_mm<=0 or thread_diameter_mm<=0 or thread_depth_mm<=0:
            raise ValueError('Dimensions must be positive')
        if feature_name and model.FeatureByName(feature_name) is not None:
            raise ValueError('Feature already exists: '+feature_name)
        import pythoncom
        from win32com.client import VARIANT
        model.ClearSelection2(True)
        picked=[]
        for point in edge_points_mm:
            if len(point)!=3:raise ValueError('Need x,y,z for each point')
            p=[v/1000 for v in point]
            best=None
            for i,edge in enumerate(edges):
                methods(edge,'GetClosestPointOn')
                q=edge.GetClosestPointOn(*p)
                if q is None:continue
                distance=sum((q[j]-p[j])**2 for j in range(3))**0.5
                if best is None or distance<best[0]:best=(distance,i,edge)
            if best is None or best[0]>0.00005:
                raise ValueError(f'No edge within 0.05 mm of {point}; nearest={best[0] if best else None}')
            if best[1] not in picked:
                methods(best[2],'Select4')
                if not best[2].Select4(True,VARIANT(pythoncom.VT_DISPATCH,None)):
                    raise RuntimeError('Edge selection failed')
                picked.append(best[1])
        fm=methods(model.FeatureManager,'FeatureFillet3','InsertCosmeticThread3')
        if operation=='fillet':
            # Exact 14-argument SW2020 signature verified from installed interop.
            feat=fm.FeatureFillet3(195,radius_mm/1000,0.0,0.0,0,0,0,None,None,None,None,None,None,None)
        else:
            if len(picked)!=1:raise ValueError('Select one circular thread edge')
            feat=fm.InsertCosmeticThread3(-2,'','',thread_diameter_mm/1000,0,thread_depth_mm/1000,note)
        model.ClearSelection2(True)
        if feat is None:raise RuntimeError(operation+' returned no feature; inspect before retry')
        if feature_name:feat.Name=feature_name
        return {'status':'success','feature':feat.Name,'operation':operation,'edge_indices':picked}
